#!/usr/local/bin/python3.6 
# -- coding: utf-8 -- –

import os,base64,re,psycopg2,threading,logging,csv,telegram,json,time,sys
import tweepy
from random import randint
from time import sleep,strftime,gmtime
from functools import wraps
from pprint import pprint
from functions import dot,Map
from telegram import InputMediaPhoto, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, RegexHandler,CallbackQueryHandler,ConversationHandler, DelayQueue,messagequeue as mqueue
from telegram.ext.dispatcher import run_async
from telethon import TelegramClient, events, sync
from telethon.tl import types, functions, tlobject
from telethon.tl.types import InputMediaPhotoExternal,MessageEntityBold,MessageEntityItalic,ChannelParticipantsSearch,InputChannel,InputUserSelf,InputUser,UpdateShortMessage,PeerUser,ChannelAdminLogEventsFilter,ChannelBannedRights,InputPeerChannel,InputPeerUser,ChannelParticipantsAdmins,ChannelParticipantsBots,SendMessageTypingAction,UserStatusLastMonth,UserStatusLastWeek,UpdateNewMessage
from telethon.tl.functions.channels import GetParticipantsRequest,GetFullChannelRequest,GetChannelsRequest,GetAdminLogRequest,EditBannedRequest,ReadHistoryRequest,GetFullChannelRequest,DeleteHistoryRequest,JoinChannelRequest,CreateChannelRequest,InviteToChannelRequest
from telethon.tl.functions.messages import SendMediaRequest,CheckChatInviteRequest,ImportChatInviteRequest,SendMessageRequest,SetTypingRequest,AddChatUserRequest,GetFullChatRequest
from telethon.tl.functions.contacts import ResolveUsernameRequest
from telethon.tl.functions.users import GetFullUserRequest,GetUsersRequest
from  telethon.utils import  get_display_name
from telethon.extensions.markdown import parse
from emoji import emojize
from PIL import Image, ImageFont, ImageDraw
# import matplotlib.pyplot as plot
# from captcha.image import ImageCaptcha
import CaptchasDotNet

# logging.basicConfig(filename='log',format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
CONFIG = {}
CHAN = {}
GROUP_JOIN_CHECK, EMAIL, CONFIRM_EMAIL, TWITTER, CONFIRMTWITTER, FACEBOOK, CONFIRM_FACEBOOK, REDDIT, CONFIRM_REDDIT,INSTAGRAM, CONFIRM_INSTAGRAM, MEDIUM, CONFIRM_MEDIUM, BOT_CHECK,GET_WELCOME_TEXT,GET_RETWEET_LINK,ADMIN_MENU,EDIT_WELCOME_TEXT,EDIT_RETWEET_LINK,END_AIRDROP_STATE,WALLET,CONFIRM_WALLET = range(22)

def loadConfig():
	global CONFIG
	with open(os.path.dirname(os.path.abspath(__file__))+'/config.json', 'r', encoding='utf-8') as f:
		CONFIG = dot(json.load(f))
	f.close()

def connectPSQL():
	conn = psycopg2.connect('dbname=%s user=%s'%(CONFIG.DB_NAME,CONFIG.DB_USER))
	conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
	cur_local = conn.cursor()
	return cur_local
	
def query(query):
	DB_LOCK.acquire()
	try:
		DB.execute(query)
	except (TypeError,ValueError,psycopg2.IntegrityError):
		logging.warning("o Error in the query: "+query)
	DB_LOCK.release()
	if (re.search('^select', query)):
		output = DB.fetchall()
		if not len(output):
			return 0
		elif len(output)>1:
			return output #[(a,b,c,..),(b,c,d,e,...)]
		else:
			if len(output[0])>1:#[(a,b,c,..),(b,c,d,e,...)]
				return [output[0],] #[(a,b,c,..),(b,c,d,e,...)]
			elif len(output[0]):
				return output[0][0] #[(a,b,c,..)]
			else:
				return 0 #0

def restricted(func):
	@wraps(func)
	def wrapped(bot, update, *args, **kwargs):
		if update.message.from_user.username not in CONFIG.ADMINS:
			logging.debug("Unauthorized access denied for {}.".format(update.message.chat.id))
			bot.send_message(update.message.chat.id,"Sorry, only admins are authorized.", timeout=30)
			return
		return func(bot, update, *args, **kwargs)
	return wrapped

def getEmoji(input):
	return emojize(input, use_aliases=True)

def botReplyInlineKeyboard (update,text,keyboard, parse_mode=telegram.ParseMode.MARKDOWN, disable_web_page_preview=True):
	reply_markup = InlineKeyboardMarkup(keyboard)
	msg = update.message.reply_text(text, reply_markup = reply_markup,  parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview, timeout=30)
	return msg.message_id

def botReplyKeyboard (update,text,keyboard, reply_markup=False, one_time_keyboard=True, parse_mode = telegram.ParseMode.MARKDOWN, resize_keyboard=True, disable_web_page_preview=True):
	if not reply_markup:
		reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard = one_time_keyboard, resize_keyboard = resize_keyboard)
	else:
		reply_markup = ReplyKeyboardRemove()
	msg = update.message.reply_text(text, reply_markup = reply_markup,  disable_web_page_preview=disable_web_page_preview, parse_mode=parse_mode, timeout=30)
	return msg.message_id

def updateDatabase():
	logging.warning("o Thread UpdateDatabase iniciou.")
	for entity in ['group','channel',]:
		query("truncate %s_users_temp"%entity)
		users = CLIENT.get_participants(CHAN[entity]['username'], aggressive=True)
		if users:
			insertQuery = "insert into %s_users_temp (userid) values  "%entity
			for user in users:
				insertQuery += "(%d),"%user.id
			query(insertQuery.rstrip(',')+" on conflict (userid) do nothing")
			left_users = query("select u.userid from (select userid from %s_users where userid not in (select userid from %s_users_temp) intersect (select userid from registered_users where inside_%s=TRUE)) u"%(entity,entity,entity))
			if left_users:
				if isinstance(left_users, list):
					for userid in left_users:
						if entity == 'group':
							leftMemberGroup(userid[0])
						else:
							leftMemberChannel(userid[0])
				else:
						if entity == 'group':
							leftMemberGroup(left_users)
						else:
							leftMemberChannel(left_users)
			if entity != 'group':
				rejoined_users = query("select u.userid from (select userid from %s_users_temp where userid not in (select userid from %s_users) intersect (select userid from registered_users where inside_%s=FALSE)) u"%(entity,entity,entity))
				if rejoined_users:
					if isinstance(rejoined_users, list):
						for userid in rejoined_users :
							rejoinMemberChannel(userid[0])
					else:
						rejoinMemberChannel(rejoined_users)
			query("truncate table %s_users"%entity)
			query("insert into %s_users (select * from %s_users_temp)"%(entity,entity))
	threading.Timer(3600, updateDatabase).start() #reinicia thread em tanto segundos
	logging.warning("o Thread updateDatabase exiting.")
	sys.exit()


def checkTwitterFollow(username):
	app = getTwitterApp()
	try:
		followers = [True for follower in tweepy.Cursor(app.followers, screen_name=CONFIG.TWITTER_USERNAME).items(100) if follower.screen_name.lower() in username.lower()]
	except:
		debug.error("o Todas as contas atingiram o limite de Twitter Follow requests.")
		return True
	return True if len(followers) else False

def checkRetweeted(username):
	app = getTwitterApp()
	username = username.lstrip('@')
	TWITTER_ID = re.search('.*\/(\d+)',RETWEET_LINK)
	try:
		retweet_check = [True for retweet in app.retweets(TWITTER_ID.group(1),100) if retweet.user.screen_name.lower() in username.lower()]
	except:
		debug.error("o Todas as contas atingiram o limite de Twitter Retweets requests.")
		return True
	return True if len(retweet_check) else False

#BOT_CHECK
@run_async
def botCheck(bot, update, user_data):
	#checar se usuario está banido
	if query("select count(*) from banned where userid = %d"%update.message.chat_id):
		return
	#checar se airdrop acabou
	if END_AIRDROP:
		text = 'This airdrop is standing by ...'
		update.message.reply_text(text, timeout=30)
		return
	#gerar ouotro captcha
	elif  "/start" in update.message.text:
		check = query ("select count(*) from registered_users where userid = %d"%update.message.chat_id)
		if check: #ja é registrado
			# out = query ("select name, last_name, email, twitter, instagram, reddit, medium from registered_users where userid = %d"%update.message.chat_id)
			# name, last_name, email, twitter, instagram, reddit, medium = out[0]
			# text = 'Welcome back!\n\n```Email: %s\nTwitter: %s\nInstagram: %s\nReddit: %s\nMedium: %s```\n\nTokens will be sent as soon as the end of this bounty.'%(email, twitter, instagram, reddit, medium)
			text = 'Welcome back!'
			keyboard = [
					[KeyboardButton("Balance %s"%getEmoji(':moneybag:'))],
					[KeyboardButton("Referral link %s"%getEmoji(':mega:'))],
					[KeyboardButton("Rank %s"%getEmoji(':fire:'))],
					[KeyboardButton("Info %s"%getEmoji(':bulb:'))]
			]
			botReplyKeyboard(update, text, keyboard, one_time_keyboard=False)
			return ConversationHandler.END
		else: # nao é registrado
			text = "Please wait ..."
			msg = bot.send_message(update.message.chat_id, text, timeout=30)
			first_msg_id = msg.message_id
			referId = 0
			input = update.message.text.split()
			if (len(input) > 1):
				referId = base64.urlsafe_b64decode(input[1]).decode('ascii')
			captchas = CaptchasDotNet.CaptchasDotNet (
	                                client   = 'owneroxxor', 
	                                secret   = 'cS35jJYp15kjQf01FVqA7ubRaNOXKPmYGRbLUiim',
	                                alphabet = 'abcdefghkmnopqrstuvwxyz',
	                                letters  = 4,
	                                width    = 240,
	                                height   = 80,
	                                color = 'f69547'
           			)
			image_url, random_word = captchas.generate()
			text = 'Write down the letters in the image:'
			keyboard = [[KeyboardButton("Generate other image %s"%getEmoji(':arrows_counterclockwise:'))]]
			reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard = True)
			try:
				msg = bot.send_photo(update.message.chat_id, caption=text, timeout=30, photo=image_url, reply_markup=reply_markup)
			except:
				msg = bot.send_photo(update.message.chat_id, caption=text, timeout=30, photo=image_url, reply_markup=reply_markup)
			user_data['previous_msg_id'] = msg.message_id
			user_data['refer_id'] = int(referId)
			user_data['captchas'] = captchas
			user_data['retries'] = 5
			deletePreviousMsg (bot,update.message.chat_id,first_msg_id)
			return BOT_CHECK
	elif "Generate other image" in update.message.text : #generate other image
		deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
		text = "Please wait ..."
		msg = bot.send_message(update.message.chat_id, text, timeout=30)
		first_msg_id = msg.message_id
		captchas = CaptchasDotNet.CaptchasDotNet (
                                client   = 'owneroxxor', 
                                secret   = 'cS35jJYp15kjQf01FVqA7ubRaNOXKPmYGRbLUiim',
                                alphabet = 'abcdefghkmnopqrstuvwxyz',
                                letters  = 4,
                                width    = 240,
                                height   = 80,
                               	color = 'f69547'
           		)
		image_url, random_word = captchas.generate()
		text = 'Write down the letters in the image:'
		keyboard = [[KeyboardButton("Generate other image %s"%getEmoji(':arrows_counterclockwise:'))]]
		reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard = True)
		try:
			msg = bot.send_photo(update.message.chat_id, caption=text, timeout=30, photo=image_url, reply_markup=reply_markup)
		except:
			msg = bot.send_photo(update.message.chat_id, caption=text, timeout=30, photo=image_url, reply_markup=reply_markup)
		user_data['previous_msg_id'] = msg.message_id
		user_data['captchas'] = captchas
		deletePreviousMsg (bot,update.message.chat_id,first_msg_id)
		return BOT_CHECK
	else: #checar palavra do captcha
		if not user_data['captchas'].verify(update.message.text):
			user_data['retries'] -= 1
			if user_data['retries'] > 0: #errou mas tem tentativas ainda
				captchas = CaptchasDotNet.CaptchasDotNet (
		                                client   = 'owneroxxor', 
		                                secret   = 'cS35jJYp15kjQf01FVqA7ubRaNOXKPmYGRbLUiim',
		                                alphabet = 'abcdefghkmnopqrstuvwxyz',
		                                letters  = 4,
		                                width    = 240,
	                                	height   = 80,
                               	 		color = 'f69547'
		           		)
				image_url, random_word = captchas.generate()
				user_data['previous_msg_id'] = deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
				msg = update.message.reply_text("Wrong match!\nYou still have %d chances."%user_data['retries'], timeout=30)
				user_data['previous_msg_id'].append(msg.message_id)
				text = 'Write down the letters in the image:'
				keyboard = [[KeyboardButton("Generate other image %s"%getEmoji(':arrows_counterclockwise:'))]]
				reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard = True)
				try:
					msg = bot.send_photo(update.message.chat_id, caption=text, timeout=30, photo=image_url, reply_markup=reply_markup)
				except:
					msg = bot.send_photo(update.message.chat_id, caption=text, timeout=30, photo=image_url, reply_markup=reply_markup)
				user_data['previous_msg_id'].append(msg.message_id)
				user_data['captchas'] = captchas
				return BOT_CHECK
			else: #esgotou as tentativas, tomou ban
				query("insert into banned (userid) values (%d) on conflict (userid) do nothing"%update.message.chat_id)
				text = "You are banned from the Airdrop."
				update.message.reply_text(text, timeout=30)
				return ConversationHandler.END
		else: #deu certo, nao é bot		
			deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
			photo = 'AgADAQADlKgxG25P8UVYMcR9vsY7W3kj9y8ABBKkxHkt98LlH3oEAAEC'
			bot.send_photo(update.message.chat_id, photo, timeout=30)
			text = '''🔥🔥🔥Hello and Welcome to HetaChain Airdrop Bot.
⭐️⭐️⭐️HetaChain: A Third Trendy Generation Blockchain Platform.
🔥🔥🔥The Rewards up to $2,000,000 in Airdrop Campaign.
☀️☀️☀️Follow The Following Rules To Get Free HETA:
🌧 Step 1: Join Our Community Group (300 HETA) ($5)
🌧 Step 2: Join HetaChain Announcement Channel (300 HETA) ($5)
🌧 Step 3: Follow on HetaChain Twitter (300 HETA) ($5)
🌧 Step 4: Reweet HetaChain's Post on Twitter (300 HETA)  ($5)
🌟🌟🌟 Extra rewards : Earn Up To $100 in HETA Through Referral Campaign. 
🌟🌟🌟120 HETA ($2) Per Each Referral . Maximum 50 Referrals)'''
			keyboard = [
					[InlineKeyboardButton("Join our Community Group %s"%getEmoji(':busts_in_silhouette:'),url=CHAN['group']['link'])],
					[InlineKeyboardButton("Join the Announcements Channel %s"%getEmoji(':loudspeaker:'),url=CHAN['channel']['link'])],
					[InlineKeyboardButton("Follow on Twitter %s"%(getEmoji(':arrow_upper_right:')), url=CONFIG.TWITTER)],
					[InlineKeyboardButton("Retweet %s"%(getEmoji(':arrow_upper_right:')), url=RETWEET_LINK)],
			]
			user_data['previous_msg_id'] = []
			user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
			text = "After doing the above tasks, click next to proceed with the registration:"
			keyboard = [
					[InlineKeyboardButton("Next %s"%getEmoji(':fast_forward:'), callback_data=user_data['refer_id'])],
			]
			user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
			return GROUP_JOIN_CHECK

#GROUP_JOIN_CHECK
@run_async
def groupJoinCheck (bot, update, user_data):
	for entity in ['group','channel']:
		user = update.callback_query.from_user.username if update.callback_query.from_user.username is not None else "%s %s"%(update.callback_query.from_user.first_name, update.callback_query.from_user.last_name if update.callback_query.from_user.last_name else "")
		if entity == 'channel': #se nao estava no grupo ainda, checa se acabou de entrar
			if not CLIENT.get_participants(CHAN[entity]['username'], limit=1, search=user):
			# param: (join, leave, invite, ban, unban, kick, unkick, promote, demote, info, settings, pinned, edit, delete)
			# _filter = ChannelAdminLogEventsFilter(True, False, False, False, False, False, False, False, False, False, False, False, False, False)
			# result = CLIENT(GetAdminLogRequest(CLIENT.get_input_entity(CHAN[entity]['username']), '', 0, 0, 50, _filter))
				text = "%s It seems you didn't join the:\n\n Announcements Channel %s\n\nComplete this task to continue."%(getEmoji(':warning:'),getEmoji(':loudspeaker:'),)
				bot.answerCallbackQuery(update.callback_query.id, text=text, show_alert=True, timeout=30)
				return GROUP_JOIN_CHECK
		elif entity == 'group':
			if not CLIENT.get_participants(CHAN[entity]['username'], limit=1, search=user):
				text = "%s It seems you didn't join the:\n\n Community Group %s\n\nComplete this task to continue."%(getEmoji(':warning:'),getEmoji(':loudspeaker:'),)
				bot.answerCallbackQuery(update.callback_query.id, text=text, show_alert=True, timeout=30)
				return GROUP_JOIN_CHECK
	bot.answerCallbackQuery(update.callback_query.id, timeout=30)
	user_data['previous_msg_id'] = deletePreviousMsg (bot,update.callback_query.message.chat_id,user_data['previous_msg_id'])
	msg = bot.send_message(update.callback_query.message.chat_id, 'Great! Now lets start the registration! %s'%getEmoji(':white_check_mark:'), reply_markup=ReplyKeyboardRemove(), timeout=30)
	user_data['previous_msg_id'].append(msg.message_id)
	text = "Now please send the ERC-20 wallet address:"
	msg = bot.send_message(update.callback_query.message.chat_id, text, timeout=30)
	user_data['previous_msg_id'].append(msg.message_id)
	return WALLET

# #EMAIL
# @run_async
# def getEmail(bot, update,user_data):
# 	deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
# 	regex = re.search('^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', update.message.text, flags=re.IGNORECASE)
# 	if regex:
# 		if not query("select count(*) from registered_users where email='%s'"%update.message.text): #email ja registrado
# 			if len(update.message.text) < 50:
# 				text = 'Do you confirm submitting\n\n%s\n\n as your e-mail address?'%update.message.text
# 				keyboard = [
# 						[KeyboardButton("Confirm %s"%getEmoji(':fast_forward:'))],
# 						[KeyboardButton("%s Go back"%getEmoji(':rewind:'))]
# 				]
# 				user_data['previous_msg_id'] = botReplyKeyboard(update, text, keyboard, parse_mode= None)
# 				user_data['email'] =  update.message.text
# 				return CONFIRM_EMAIL
# 			else:
# 				msg = update.message.reply_text('Emal address too long.\nPlease send other e-mail address:', reply_markup= ReplyKeyboardRemove(), timeout=30)
# 				user_data['previous_msg_id'] = msg.message_id
# 				return EMAIL
# 		else:
# 			msg = update.message.reply_text('This email address was already registered in this Bounty.\nPlease send other e-mail address:', reply_markup= ReplyKeyboardRemove(), timeout=30)
# 			user_data['previous_msg_id'] = msg.message_id
# 			return EMAIL
# 	else:
# 		msg = update.message.reply_text('Invalid e-mail address.\nPlease send e-mail again:', reply_markup= ReplyKeyboardRemove(), timeout=30)
# 		user_data['previous_msg_id'] = msg.message_id
# 		return EMAIL

# #CONFIRM_EMAIL
# @run_async
# def confirmEmail(bot, update, user_data):
# 	user_data['previous_msg_id'] = deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
# 	if "Confirm " in update.message.text:
# 		text = "Now please send the ERC20 wallet address:"
# 		keyboard = [
# 				[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
# 		return WALLET
# 	else:
# 		msg =update.message.reply_text('Declined!\nSubmit the new e-mail address:', reply_markup=ReplyKeyboardRemove(), timeout=30)
# 		user_data['previous_msg_id'] .append(msg.message_id)
# 		return EMAIL

#WALLET
@run_async
def getWallet(bot, update, user_data):
	user_data['previous_msg_id'] = deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
	# if " Previous" in update.message.text:
	# 	text  = 'Ok, back to the begining...%s'%getEmoji(':white_check_mark:')
	# 	user_data['previous_msg_id'].append(botReplyKeyboard(update,text,0, reply_markup = ReplyKeyboardRemove()))
	# 	text = 'Send the e-mail address you used to sign up on our website:'
	# 	keyboard = [
	# 			[InlineKeyboardButton("Sign up on the Website %s"%getEmoji(':pencil2:'), url="%s"%CONFIG.WEBSITE)],
	# 	]
	# 	user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
	# 	return EMAIL
	if re.search('^(0x)?[0-9a-f]{40}$', update.message.text,  flags=re.IGNORECASE):
		flag = query("select count (*) from registered_users where wallet='%s'"%update.message.text)
		if flag:
			text = 'This wallet is already taken in this bounty.\nPlease, use another wallet address:'
			msg = update.message.reply_text(text, timeout=30)
			user_data['previous_msg_id'].append(msg.message_id)
			return WALLET
		text = 'Do you confirm submitting\n\n`%s`\n\nas your wallet address?'%update.message.text
		keyboard = [
				[KeyboardButton("Confirm %s"%getEmoji(':fast_forward:'))],
				[KeyboardButton("%s Go back"%getEmoji(':rewind:'))]
		]
		user_data['previous_msg_id'].append(botReplyKeyboard(update, text, keyboard))
		user_data['wallet'] = update.message.text
		return CONFIRM_WALLET
	else:
		update.message.reply_text('Invalid wallet address.\nPlease send a new wallet address (ERC-20):', reply_markup= ReplyKeyboardRemove(), timeout=30)
		return WALLET

#CONFIRM_WALLET
@run_async
def confirmWallet(bot, update,user_data):
	user_data['previous_msg_id'] = deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
	text = update.message.text
	if "Confirm" in text:
		text = 'Have you already followed us on Twitter and retweeted the below post?'
		keyboard = [
				[InlineKeyboardButton("Follow us on Twitter %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.TWITTER)],
				[InlineKeyboardButton("Retweet post %s"%getEmoji(':arrow_upper_right:'),url=RETWEET_LINK)],
		]
		user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
		keyboard = [
				[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
		]
		text = "Then send me your Twitter username (@username):"
		user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
		return TWITTER
	else:
		msg = bot.send_message(update.message.chat_id, 'Declined!\nPlease insert the new wallet address (ERC-20):', reply_markup=ReplyKeyboardRemove())
		user_data['previous_msg_id'] .append(msg.message_id)
		return WALLET

#TWITTER
@run_async
def getTwitter(bot, update, user_data):
	user_data['previous_msg_id'] = deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
	if "Next " in update.message.text:
		if 'twitter' in user_data:
			# if not checkTwitterFollow(user_data['twitter']):
			if not True:
				text = "This username is not yet following us on Twitter."
				keyboard = [
					[InlineKeyboardButton("Follow us on Twitter %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.TWITTER)],
				]
				user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
				text = 'Please complete this task and hit next. Or type down a new Twitter username: '
				keyboard = 	[
						[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
						[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
				]
				user_data['previous_msg_id'].append(botReplyKeyboard(update, text, keyboard))
				return TWITTER
			elif query("select count(*) from registered_users where twitter = '%s'"%user_data['twitter']): #ja existe alguem cadastrado com esse twitter
				text = 'This twitter username is already taken. Please send another:'
				keyboard = 	[
					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
				]
				user_data['previous_msg_id'].append(botReplyKeyboard(update, text, keyboard))
				return TWITTER
			elif not True:
				pass
				# elif not checkRetweeted(user_data['twitter']):
				# 	text = "This username did not retweet the following post yet:"
				# 	keyboard = [
				# 		[InlineKeyboardButton("Retweet post %s"%getEmoji(':arrow_upper_right:'),url=RETWEET_LINK)],
				# 	]
				# 	user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
				# 	text = 'Please complete this task and hit next. Or type down a new Twitter username: '
				# 	keyboard = 	[
				# 		[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
				# 		[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
				# 	]
				# 	user_data['previous_msg_id'].append(botReplyKeyboard(update, text, keyboard))
				# 	return TWITTER
			else: #esta seguindo no twitter e retweetou
				# text = 'Have you already followed us on Instagram? (earn +100 {}):'.format(CONFIG.TOKEN)
				# keyboard = [
				# 		[InlineKeyboardButton("Follow us on Instagram %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.INSTAGRAM)],
				# ]
				# user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
				# keyboard = 	[
				# 			[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
				# 			[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
				# ]
				# text = "Then send me your Instagram username. Or just hit next if you don't have an Instagram account."
				# user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
				# return INSTAGRAM	
				regex = re.search("(\S{2})$",update.message.from_user.language_code)
				country =regex.group(1) if regex else ""
				country = country.replace("'","''")
				print(update.message.from_user.first_name, update.message.from_user.last_name, update.message.from_user.username, user_data['refer_id'], user_data['wallet'], user_data['twitter'])
				query('''insert into registered_users (userid, 
																			joindate, 
																			country, 
																			name, 
																			last_name, 
																			username, 
																			invitedbyuserid,
																			wallet, 
																			twitter) values (%d,current_timestamp,'%s','%s','%s','%s',%d,'%s','%s') on conflict (userid) do nothing'''%(update.message.chat_id,
																																																																						country,
																																																																						update.message.from_user.first_name,
																																																																						update.message.from_user.last_name, 
																																																																						update.message.from_user.username, 
																																																																						user_data['refer_id'], 
																																																																						user_data['wallet'], 
																																																																						user_data['twitter']))
				if user_data['refer_id'] :
					query("update registered_users set affiliates = affiliates+1 where userid = %d"%user_data['refer_id'])
					affiliates = query("select affiliates from registered_users where userid = %d"%user_data['refer_id'])
					text = '''_A person just registered with your referral link.\n\nYour referrals:_  `{}` _referrals_
_Your new balance:_ `{:,}` {}'''.format(affiliates, calcBalance(user_data['refer_id']),CONFIG.TOKEN)
					bot.send_message(user_data['refer_id'], text=text, parse_mode=telegram.ParseMode.MARKDOWN, timeout=30)
				text = '''Congratulations! %s
You are registered. %s

Wallet: `%s`
Twitter: `%s`
Balance: `%d %s`

Tokens will be sent as soon as the end of this airdrop. Stay linked for the next announcements to come.'''%(getEmoji(':checkered_flag:'),
																																										getEmoji(':thumbsup:'), 
																																										user_data['wallet'],
																																										user_data['twitter'],
																																										calcBalance(update.message.chat_id),
																																										CONFIG.TOKEN)
				keyboard = [
						[KeyboardButton("Balance %s"%getEmoji(':moneybag:'))],
						[KeyboardButton("Referral link %s"%getEmoji(':mega:'))],
						[KeyboardButton("Rank %s"%getEmoji(':fire:'))],
						[KeyboardButton("Info %s"%getEmoji(':bulb:'))]
				]
				botReplyKeyboard(update, text, keyboard, one_time_keyboard=False)
				return ConversationHandler.END


	elif " Previous" in update.message.text:
		msg  = bot.send_message(update.message.chat_id, text='Ok, back one step...%s'%getEmoji(':white_check_mark:'), reply_markup=ReplyKeyboardRemove(), timeout=30)
		user_data['previous_msg_id'].append(msg.message_id)
		text = "Please send the ERC20 wallet address:"
		msg = update.message.reply_text(text, timeout=30)
		user_data['previous_msg_id'].append(msg.message_id)
		return WALLET
	else:
		regex = re.search('^(@\w{1,15})$', update.message.text, flags=re.IGNORECASE)
		if regex:
			user_data['twitter'] = update.message.text.lower()
			# if not checkTwitterFollow(regex.group(1)):
			if not True:
				text = "This username is not yet following us on Twitter."
				keyboard = [
					[InlineKeyboardButton("Follow us on Twitter %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.TWITTER)],
				]
				user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
				text = 'Please complete this task and hit next. Or type down a new Twitter username: '
				keyboard = 	[
						[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
						[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
				]
				user_data['previous_msg_id'].append(botReplyKeyboard(update, text, keyboard))
				return TWITTER
			elif query("select count(*) from registered_users where twitter = lower('%s')"%update.message.text): #ja existe alguem cadastrado com esse twitter
				text = 'This twitter username is already taken. Please send another:'
				keyboard = 	[
					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
				]
				user_data['previous_msg_id'].append(botReplyKeyboard(update, text, keyboard))
				return TWITTER
			elif not True:
				pass
				# elif not checkRetweeted(regex.group(1)):
				# 	text = "This username did not retweet the following post yet:"
				# 	keyboard = [
				# 		[InlineKeyboardButton("Retweet post %s"%getEmoji(':arrow_upper_right:'),url=RETWEET_LINK)],
				# 	]
				# 	user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
				# 	text = 'Please complete this task and hit next. Or type down a new Twitter username: '
				# 	keyboard = 	[
				# 		[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
				# 		[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
				# 	]
				# 	user_data['previous_msg_id'].append(botReplyKeyboard(update, text, keyboard))
				# 	return TWITTER
			else: #esta seguindo no twitter e retweetou
				# text = 'Have you already followed us on Instagram? (earn +100 {}):'.format(CONFIG.TOKEN)
				# keyboard = [
				# 		[InlineKeyboardButton("Follow us on Instagram %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.INSTAGRAM)],
				# ]
				# user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
				# keyboard = 	[
				# 			[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
				# 			[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
				# ]
				# text = "Then send me your Instagram username. Or just hit next if you don't have an Instagram account."
				# user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
				# return INSTAGRAM	

				regex = re.search("(\S{2})$",update.message.from_user.language_code)
				country = regex.group(1) if regex else ""
				country = country.replace("'","''")
				print(update.message.from_user.first_name, update.message.from_user.last_name, update.message.from_user.username, user_data['refer_id'], user_data['wallet'], user_data['twitter'])
				query('''insert into registered_users (userid, 
																			joindate, 
																			country, 
																			name, 
																			last_name, 
																			username, 
																			invitedbyuserid,
																			wallet, 
																			twitter) values (%d,current_timestamp,'%s','%s','%s','%s',%d,'%s','%s') on conflict (userid) do nothing'''%(update.message.chat_id,
																																																																						country,
																																																																						update.message.from_user.first_name,
																																																																						update.message.from_user.last_name, 
																																																																						update.message.from_user.username, 
																																																																						user_data['refer_id'], 
																																																																						user_data['wallet'], 
																																																																						user_data['twitter']))
				if user_data['refer_id'] :
					query("update registered_users set affiliates = affiliates+1 where userid = %d"%user_data['refer_id'])
					affiliates = query("select affiliates from registered_users where userid = %d"%user_data['refer_id'])
					text = '''_A person just registered with your referral link.\n\nYour referrals:_ `{} referrals`
_Your new balance:_ `{:,} {}`'''.format(affiliates, calcBalance(user_data['refer_id']), CONFIG.TOKEN)
					bot.send_message(user_data['refer_id'], text=text, parse_mode=telegram.ParseMode.MARKDOWN, timeout=30)
				text = '''Congratulations! %s
You are registered. %s

Wallet: `%s`
Twitter: `%s`
Balance: `%d %s`

Tokens will be sent as soon as the end of this airdrop. Stay linked for the next announcements to come.'''%(getEmoji(':checkered_flag:'),
																																										getEmoji(':thumbsup:'), 
																																										user_data['wallet'],
																																										user_data['twitter'],
																																										calcBalance(update.message.chat_id),
																																										CONFIG.TOKEN)
				keyboard = [
						[KeyboardButton("Balance %s"%getEmoji(':moneybag:'))],
						[KeyboardButton("Referral link %s"%getEmoji(':mega:'))],
						[KeyboardButton("Rank %s"%getEmoji(':fire:'))],
						[KeyboardButton("Info %s"%getEmoji(':bulb:'))]
				]
				botReplyKeyboard(update, text, keyboard, one_time_keyboard=False)
				return ConversationHandler.END

		else:
			text = "Invalid Twitter username. Please, send other Twitter username:"
			keyboard = 	[
					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
			]
			user_data['previous_msg_id'] = botReplyKeyboard(update,text,keyboard)
			return TWITTER
	
# #FACEBOOK
# @run_async
# def getFacebook(bot, update,user_data):
# 	deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
# 	if "Next " in update.message.text:
# 		user_data['facebook'] = ""
# 		user_data['previous_msg_id'] = []
# 		text = 'Have you already followed us on Instagram? (earn +100 {}):'.format(CONFIG.TOKEN)
# 		keyboard = [
# 				[InlineKeyboardButton("Follow us on Instagram %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.INSTAGRAM)],
# 		]
# 		user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
# 		keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = "Then send me your Instagram username.\nOr just hit next if you don't have an Instagram account."
# 		user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
# 		return INSTAGRAM
# 	elif " Previous" in update.message.text:
# 		user_data['previous_msg_id'] = []
# 		msg = bot.send_message(update.message.chat_id, text='Ok, one step back...%s'%getEmoji(':white_check_mark:'), reply_markup=ReplyKeyboardRemove(), timeout=30)
# 		user_data['previous_msg_id'].append(msg.message_id)
# 		text = 'Have you already followed us on Twitter and retweeted the below post? (earn +100 {}):'.format(CONFIG.TOKEN)
# 		keyboard = [
# 				[InlineKeyboardButton("Follow us on Twitter %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.TWITTER)],
# 				[InlineKeyboardButton("Retweet post %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.RETWEET)],
# 		]
# 		user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
# 		keyboard = [
# 				[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 				[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = "Then send me your retweeted link.\nOr just hit next if you don't have a Twitter account."
# 		user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
# 		return TWITTER
# 	else:
# 		regex = re.search('^https:\/\/.*', update.message.text, flags=re.IGNORECASE)
# 		if regex and len(update.message.text)<=255:
# 			text = 'Do you confirm submitting *%s* as your Facebook profile link?'%update.message.text
# 			keyboard = [
# 					[KeyboardButton("Confirm %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Go back"%getEmoji(':rewind:'))]
# 			]
# 			user_data['previous_msg_id'] = botReplyKeyboard(update, text, keyboard)
# 			user_data['facebook'] = update.message.text
# 			return CONFIRM_FACEBOOK
# 		else:
# 			keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 			]
# 			text = 'Invalid Facebook profile link.\nPlease send Facebook profile link again, or hit next for skipping.'
# 			user_data['previous_msg_id'] = botReplyKeyboard(update,text,keyboard)
# 			return FACEBOOK

# #CONFIRM_FACEBOOK
# @run_async
# def confirmFacebook(bot, update,user_data):
# 	deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
# 	text = update.message.text
# 	if "Confirm " in text:
# 		user_data['previous_msg_id'] = []
# 		text = 'Have you already followed us on Instagram? (earn +100 {}):'.format(CONFIG.TOKEN)
# 		keyboard = [
# 				[InlineKeyboardButton("Follow us on Instagram %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.INSTAGRAM)],
# 		]
# 		user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
# 		keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = "Then send me your Instagram profile username.\nOr just hit next if you don't have an Instagram account."
# 		user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
# 		return INSTAGRAM
# 	else:
# 		keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = 'Declined!\nPlease insert the new Facebook profile link, or hit next for skipping.'
# 		user_data['previous_msg_id'] = botReplyKeyboard(update,text,keyboard)
# 		return FACEBOOK

# #INSTAGRAM
# @run_async
# def getInstagram(bot, update,user_data):
# 	user_data['previous_msg_id'] = deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
# 	if "Next " in update.message.text:
# 		user_data['instagram'] = ""
# 		text = 'Have you already followed us on Reddit? (earn +100 {}):'.format(CONFIG.TOKEN)
# 		keyboard = [
# 				[InlineKeyboardButton("Follow us on Reddit %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.REDDIT)],
# 		]
# 		user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
# 		keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = "Then send me your Reddit username. Or just hit next if you don't have an Reddit account."
# 		user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
# 		return REDDIT
# 	elif " Previous" in update.message.text:
# 		msg = bot.send_message(update.message.chat_id, text='Ok, one step back...%s'%getEmoji(':white_check_mark:'), reply_markup=ReplyKeyboardRemove(), timeout=30)
# 		user_data['previous_msg_id'].append(msg.message_id)
# 		text = 'Have you already followed us on Twitter and retweeted the below post?'.format(CONFIG.TOKEN)
# 		keyboard = [
# 				[InlineKeyboardButton("Follow us on Twitter %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.TWITTER)],
# 				[InlineKeyboardButton("Retweet post %s"%getEmoji(':arrow_upper_right:'),url=RETWEET_LINK)],
# 		]
# 		user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
# 		keyboard = [
# 				[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = "Then send me your Twitter username:"
# 		user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
# 		return TWITTER
# 	else:
# 		regex = re.search('^@?([A-Za-z0-9_](?:(?:[A-Za-z0-9_]|(?:\.(?!\.))){0,28}(?:[A-Za-z0-9_]))?)$', update.message.text, flags=re.IGNORECASE)
# 		if regex and len(update.message.text)<=255:
# 			text = 'Do you confirm submitting\n\n%s\n\nas your Instagram username?'%update.message.text
# 			keyboard = [
# 					[KeyboardButton("Confirm %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Go back"%getEmoji(':rewind:'))]
# 			]
# 			user_data['previous_msg_id'] = botReplyKeyboard(update, text, keyboard, parse_mode= None)
# 			user_data['instagram'] = regex.group(1)
# 			return CONFIRM_INSTAGRAM
# 		else:
# 			keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 			]
# 			text = 'Invalid Instagram username.\nPlease send Instagram username again, or hit next for skipping.'
# 			user_data['previous_msg_id'] = botReplyKeyboard(update,text,keyboard)
# 			return INSTAGRAM

# #CONFIRM_INSTAGRAM
# @run_async
# def confirmInstagram(bot, update,user_data):
# 	user_data['previous_msg_id'] = deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
# 	text = update.message.text
# 	if "Confirm " in text:
# 		text = 'Have you already followed us on Reddit? (earn +100 {}):'.format(CONFIG.TOKEN)
# 		keyboard = [
# 				[InlineKeyboardButton("Follow us on Reddit %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.MEDIUM)],
# 		]
# 		user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
# 		keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = "Then send me your Reddit profile username. Or just hit next if you don't have an Reddit account."
# 		user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
# 		return REDDIT
# 	else:
# 		keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = 'Declined!\nPlease insert the new Instagram username, or hit next for skipping.'
# 		user_data['previous_msg_id'] = botReplyKeyboard(update,text,keyboard)
# 		return INSTAGRAM

# #REDDIT
# @run_async
# def getReddit(bot, update,user_data):
# 	user_data['previous_msg_id'] = deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
# 	if "Next " in update.message.text:
# 		user_data['reddit'] = ""
# 		text = 'Have you already followed us on Medium? (earn +100 {}):'.format(CONFIG.TOKEN)
# 		keyboard = [
# 				[InlineKeyboardButton("Follow us on Medium %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.MEDIUM)],
# 		]
# 		user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
# 		keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = "Then send me your Medium username. Or just hit next if you don't have a Medium account."
# 		user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
# 		return MEDIUM
# 	elif " Previous" in update.message.text:
# 		msg = bot.send_message(update.message.chat_id, text='Ok, one step back...%s'%getEmoji(':white_check_mark:'), reply_markup=ReplyKeyboardRemove(), timeout=30)
# 		user_data['previous_msg_id'].append(msg.message_id)
# 		text = 'Have you already followed us on Instagram? (earn +100 {}):'.format(CONFIG.TOKEN)
# 		keyboard = [
# 				[InlineKeyboardButton("Follow us on Instagram %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.INSTAGRAM)],
# 		]
# 		user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
# 		keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = "Then send me your Instagram username. Or just hit next if you don't have a Instagram account."
# 		user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
# 		return INSTAGRAM	
# 	else:
# 		regex = re.search('^@?(\/u\/)?([A-Za-z0-9_-]{3,20})$', update.message.text, flags=re.IGNORECASE)
# 		if regex:
# 			text = 'Do you confirm submitting\n\n%s\n\n as your Reddit username?'%update.message.text
# 			keyboard = [
# 					[KeyboardButton("Confirm %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Go back"%getEmoji(':rewind:'))]
# 			]
# 			user_data['previous_msg_id'] = botReplyKeyboard(update, text, keyboard, parse_mode = None)
# 			user_data['reddit'] = regex.group(2)
# 			return CONFIRM_REDDIT
# 		else:
# 			keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 			]
# 			text = 'Invalid Reddit username\nPlease send Reddit username again, or hit next for skipping.'
# 			user_data['previous_msg_id'] = botReplyKeyboard(update,text,keyboard)
# 			return REDDIT

# #CONFIRM_REDDIT
# @run_async
# def confirmReddit(bot, update,user_data):
# 	user_data['previous_msg_id'] = deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
# 	text = update.message.text
# 	if "Confirm " in text:
# 		text = 'Have you already followed us on Medium? (earn +100 {}):'.format(CONFIG.TOKEN)
# 		keyboard = [
# 				[InlineKeyboardButton("Follow us on Medium %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.MEDIUM)],
# 		]
# 		user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
# 		keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = "Then send me your Medium profile username. Or just hit next if you don't have a Medium account."
# 		user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
# 		return MEDIUM
# 	else:
# 		keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = 'Declined!\nPlease insert the new Reddit username, or hit next for skipping.'
# 		user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
# 		return REDDIT

# #MEDIUM
# @run_async
# def getMedium(bot, update,user_data):
# 	if not 'email' in user_data:
# 		text = 'The bot rebooted since your registration started.\nWe are sorry for that. Please, restart you registration.'
# 		update.message.reply_text(text)
# 		return BOT_CHECK
# 	user_data['previous_msg_id'] = deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
# 	if "Next " in update.message.text:
# 		user_data['medium'] = ""
# 		regex = re.search("(\S{2})$",update.message.from_user.language_code)
# 		country =regex.group(1) if regex else ""
# 		query("insert into registered_users (userid,joindate,country,name,last_name,username,invitedbyuserid,email,wallet,twitter,instagram,reddit,medium) values (%d,current_timestamp,'%s','%s','%s','%s',%d,'%s','%s','%s','%s','%s','%s') on conflict (userid) do nothing"%(update.message.chat_id,country,update.message.from_user.first_name,update.message.from_user.last_name, update.message.from_user.username, user_data['refer_id'], user_data['email'],  user_data['wallet'], user_data['twitter'], user_data['instagram'], user_data['reddit'], user_data['medium']))
# 		if user_data['refer_id'] :
# 			query("update registered_users set affiliates = affiliates+1 where userid = %d"%user_data['refer_id'])
# 			affiliates = query("select affiliates from registered_users where userid = %d"%user_data['refer_id'])
# 			text = "_A person just registered with your referral link.\n\nYour new score: %d referrals \n"%affiliates+"Your new balance: {:,} {}_".format(calcBalance(user_data['refer_id']),CONFIG.TOKEN)
# 			bot.send_message(user_data['refer_id'], text=text, parse_mode=telegram.ParseMode.MARKDOWN, timeout=30)
# 		text = 'Congratulations! %s\nYou are registered.%s\n\n`Email: %s\nWallet: %s\nTwitter: %s\nInstagram: %s\nReddit: %s\nMedium: %s`\n\nTokens will be sent as soon as the end of this bounty. Stay linked for the next announcements to come.'%(getEmoji(':checkered_flag:'),getEmoji(':thumbsup:'), user_data['email'], user_data['wallet'],user_data['twitter'], user_data['instagram'],user_data['reddit'], user_data['medium'])
# 		keyboard = [
# 				[KeyboardButton("Balance %s"%getEmoji(':moneybag:'))],
# 				[KeyboardButton("Referral link %s"%getEmoji(':mega:'))],
# 				[KeyboardButton("Rank %s"%getEmoji(':fire:'))],
# 				[KeyboardButton("Info %s"%getEmoji(':bulb:'))]
# 		]
# 		user_data['previous_msg_id'].append(botReplyKeyboard(update, text, keyboard,one_time_keyboard=False))
# 		return ConversationHandler.END
# 	elif " Previous" in update.message.text:
# 		msg = bot.send_message(update.message.chat_id, text='Ok, one step back...%s'%getEmoji(':white_check_mark:'), reply_markup=ReplyKeyboardRemove(), timeout=30)
# 		user_data['previous_msg_id'].append(msg.message_id)
# 		text = 'Have you already followed us on Reddit? (earn +100 {}):'.format(CONFIG.TOKEN)
# 		keyboard = [
# 				[InlineKeyboardButton("Follow us on Reddit %s"%getEmoji(':arrow_upper_right:'),url=CONFIG.REDDIT)],
# 		]
# 		user_data['previous_msg_id'].append(botReplyInlineKeyboard(update,text,keyboard))
# 		keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = "Then send me your Reddit profile username. Or just hit next if you don't have an Reddit account."
# 		user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
# 		return REDDIT
# 	else:
# 		regex = re.search('^@?([A-Za-z0-9_-]{1,30})$', update.message.text, flags=re.IGNORECASE)
# 		if regex:
# 			text = 'Do you confirm submitting\n\n%s\n\n as your Medium username?'%update.message.text
# 			keyboard = [
# 					[KeyboardButton("Confirm %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Go back"%getEmoji(':rewind:'))]
# 			]
# 			user_data['previous_msg_id'].append(botReplyKeyboard(update, text, keyboard, parse_mode=None))
# 			user_data['medium'] = regex.group(1)
# 			return CONFIRM_MEDIUM
# 		else:
# 			keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 			]
# 			text = 'Invalid Medium username.\nPlease send Medium username again, or hit next for skipping.'
# 			user_data['previous_msg_id'].append(botReplyKeyboard(update,text,keyboard))
# 			return MEDIUM

# #CONFIRM_MEDIUM
# @run_async
# def confirmMedium(bot, update,user_data):
# 	if not 'refer_id' in user_data:
# 		user_data['refer_id'] = 0
# 	deletePreviousMsg (bot,update.message.chat_id,user_data['previous_msg_id'])
# 	text = update.message.text
# 	if "Confirm " in text:
# 		regex = re.search("(\S{2})$",update.message.from_user.language_code)
# 		country =regex.group(1) if regex else ""
# 		print ("")
# 		print(update.message.from_user.first_name,update.message.from_user.last_name, update.message.from_user.username, user_data['refer_id'], user_data['email'],  user_data['wallet'], user_data['twitter'], user_data['instagram'], user_data['reddit'], user_data['medium'])
# 		query("insert into registered_users (userid,joindate,country,name,last_name,username,invitedbyuserid,email,wallet,twitter,instagram,reddit,medium) values (%d,current_timestamp,'%s','%s','%s','%s',%d,'%s','%s','%s','%s','%s','%s') on conflict (userid) do nothing"%(update.message.chat_id,country,update.message.from_user.first_name,update.message.from_user.last_name, update.message.from_user.username, user_data['refer_id'], user_data['email'],  user_data['wallet'], user_data['twitter'], user_data['instagram'], user_data['reddit'], user_data['medium']))
# 		if user_data['refer_id'] :
# 			query("update registered_users set affiliates = affiliates+1 where userid = %d"%user_data['refer_id'])
# 			affiliates = query("select affiliates from registered_users where userid = %d"%user_data['refer_id'])
# 			text = "_A person just registered with your referral link.\n\nYour new score: %d referrals \n"%affiliates+"Your new balance: {:,} {}_".format(calcBalance(user_data['refer_id']),CONFIG.TOKEN)
# 			bot.send_message(user_data['refer_id'], text=text, parse_mode=telegram.ParseMode.MARKDOWN, timeout=30)
# 		text = 'Congratulations! %s\nYou are registered.%s\n\n`Email: %s\nWallet: %s\nTwitter: %s\nInstagram: %s\nReddit: %s\nMedium: %s`\n\nTokens will be sent as soon as the end of this bounty. Stay linked for the next announcements to come.'%(getEmoji(':checkered_flag:'),getEmoji(':thumbsup:'), user_data['email'], user_data['wallet'], user_data['twitter'], user_data['instagram'],user_data['reddit'], user_data['medium'])
# 		keyboard = [
# 				[KeyboardButton("Balance %s"%getEmoji(':moneybag:'))],
# 				[KeyboardButton("Referral link %s"%getEmoji(':mega:'))],
# 				[KeyboardButton("Rank %s"%getEmoji(':fire:'))],
# 				[KeyboardButton("Info %s"%getEmoji(':bulb:'))]
# 		]
# 		botReplyKeyboard(update, text, keyboard,one_time_keyboard=False)
# 		return ConversationHandler.END
# 	else:
# 		keyboard = 	[
# 					[KeyboardButton("Next %s"%getEmoji(':fast_forward:'))],
# 					[KeyboardButton("%s Previous"%getEmoji(':rewind:'))]
# 		]
# 		text = 'Declined!\nPlease insert the new Medium username, or hit next for skipping.'
# 		botReplyKeyboard(update,text,keyboard)
# 		return MEDIUM

@run_async
def cancel(bot, update):
	text = 'Exited.'
	keyboard = [
				[KeyboardButton("Balance %s"%getEmoji(':moneybag:'))],
				[KeyboardButton("Referral link %s"%getEmoji(':mega:'))],
				[KeyboardButton("Rank %s"%getEmoji(':fire:'))],
				[KeyboardButton("Info %s"%getEmoji(':bulb:'))]
	]
	botReplyKeyboard(update, text, keyboard, one_time_keyboard=False)

@run_async
def echoRank(bot,update):
	output = query("select userid, name, affiliates from registered_users where affiliates >= 0 order by affiliates desc limit 15")
	if output:
		text = getEmoji(':fire:')+" *TOP 15 RANKED USERS:*\n"
		i = 1
		for x in output:
			userid,name,affiliates = x
			text += "\n*%d*"%(i)+"-`{:.6}**`".format(name if name else "unknown")+str(affiliates)+" - *{:,} {}*".format(calcBalance(userid),CONFIG.TOKEN)+"{}".format(getEmoji(':trophy:') if i <= 3 else "")
			i = i+1
		bot.send_message(update.message.chat_id, text = text,  parse_mode=telegram.ParseMode.MARKDOWN , timeout=30)
		# text = "%s The top 1 user will receive an extra 100,000 %s bonus!\n%s The top 2 user will receive an extra 50,000 %s bonus!\n%s The top 3 user will receive an extra 25,000 %s bonus!\n%s The next 10 users will receive a bonus of 10,000 %s each.\n\n"%(getEmoji(':exclamation:'),CONFIG.TOKEN,getEmoji(':exclamation:'),CONFIG.TOKEN,getEmoji(':exclamation:'),CONFIG.TOKEN,getEmoji(':exclamation:'),CONFIG.TOKEN)
		# bot.send_message(update.message.chat_id, text = text,  parse_mode=telegram.ParseMode.MARKDOWN, timeout=30 )
	else:
		update.message.reply_text("No one invited any user yet.", timeout=30)

def calcBalance(userid):
	balance = CONFIG.JOIN_TOKEN_VALUE
	affiliates = query("select affiliates from registered_users where userid=%d"%userid)
	affiliates = 50 if affiliates > 50 else affiliates
	balance += affiliates*CONFIG.REFERRAL_TOKEN_VALUE
	return balance

@run_async
def echoInfo(bot, update):
	text = '''🔥🔥🔥Hello and Welcome to HetaChain Airdrop Bot.
⭐️⭐️⭐️HetaChain: A Third Trendy Generation Blockchain Platform.
🔥🔥🔥The Rewards up to $2,000,000 in Airdrop Campaign.
☀️☀️☀️Follow The Following Rules To Get Free HETA:
🌧 Step 1: Join Our Community Group (300 HETA) ($5)
🌧 Step 2: Join HetaChain Announcement Channel (300 HETA) ($5)
🌧 Step 3: Follow on HetaChain Twitter (300 HETA) ($5)
🌧 Step 4: Reweet HetaChain's Post on Twitter (300 HETA)  ($5)
🌟🌟🌟 Extra rewards : Earn Up To $100 in HETA Through Referral Campaign. 
🌟🌟🌟120 HETA ($2) Per Each Referral . Maximum 50 Referrals)'''
	keyboard = [
			[InlineKeyboardButton("Join our Community Group %s"%getEmoji(':busts_in_silhouette:'),url=CHAN['group']['link'])],
			[InlineKeyboardButton("Join the Announcements Channel %s"%getEmoji(':loudspeaker:'),url=CHAN['channel']['link'])],
			[InlineKeyboardButton("Follow on Twitter %s"%(getEmoji(':arrow_upper_right:')), url=CONFIG.TWITTER)],
			[InlineKeyboardButton("Retweet %s"%(getEmoji(':arrow_upper_right:')), url=RETWEET_LINK)],
	]
	botReplyInlineKeyboard(update,text,keyboard)

@run_async
def echoBalance(bot, update):
	affiliates = query("select affiliates from registered_users where userid = %d"%update.message.from_user.id)
	if affiliates:
		update.message.reply_text('You have `{:d}` referrals.\nAccumulated balance: `{:,} {}`'.format(affiliates,calcBalance(update.message.from_user.id), CONFIG.TOKEN), parse_mode = telegram.ParseMode.MARKDOWN, timeout=30)
	else:
		if not query("select count(*) from registered_users where userid=%d"%update.message.from_user.id):
			update.message.reply_text("You are not registered yet.\nPlease start talking to our bot to register: %s"%CHAN['bot']['username'], timeout=30)
			return
		referral_code = base64.urlsafe_b64encode(str(update.message.from_user.id).encode('UTF-8')).decode('ascii')
		update.message.reply_text('Accumulated balance: `{:,} {}`\n\nIncrease your tokens balance by sharing your referral link.'.format(calcBalance(update.message.from_user.id), CONFIG.TOKEN), parse_mode = telegram.ParseMode.MARKDOWN, timeout=30)
		text = '%s?start=%s'%(CHAN['bot']['link'], referral_code)
		referral_link = '%s?start=%s'%(CHAN['bot']['share'],referral_code)
		inlineKeyboard = [[InlineKeyboardButton("Share", url = referral_link,),],]
		reply_markup = InlineKeyboardMarkup(inlineKeyboard)
		update.message.reply_text(text, reply_markup = reply_markup, timeout=30, disable_web_page_preview=True)

@run_async
def echoReferralLink(bot, update):
	if not query("select count(*) from registered_users where userid=%d"%update.message.from_user.id):
		update.message.reply_text("You are not registered yet.\nPlease start talking to our bot to register: %s"%CHAN['bot']['username'], timeout=30)
		return
	referral_code = base64.urlsafe_b64encode(str(update.message.chat_id).encode('UTF-8')).decode('ascii')
	text = '%s?start=%s'%(CHAN['bot']['link'], referral_code)
	referral_link = '%s?start=%s'%(CHAN['bot']['share'],referral_code)
	inlineKeyboard = [[InlineKeyboardButton("Share", url = referral_link,),],]
	reply_markup = InlineKeyboardMarkup(inlineKeyboard)
	update.message.reply_text(text, reply_markup = reply_markup, disable_web_page_preview=True, timeout=30)

@run_async
def joinMemberGroup(bot, update):
	query("insert into group_users (userid) values (%d) on conflict do nothing"%update.message.new_chat_members[0].id)
	if query("select count(*) from registered_users where userid =%d"%update.message.new_chat_members[0].id): #se usuario entrou no grupo e tinha registro
		query("update registered_users set inside_group = TRUE where userid =%d"%update.message.new_chat_members[0].id)
		query("update statistics set left_group_registered = left_group_registered-1")
		text = "_%s You made the right choice. Be welcome to our group again._"%(getEmoji(':white_check_mark:'))
		keyboard = [
				[KeyboardButton("Balance %s"%getEmoji(':moneybag:'))],
				[KeyboardButton("Referral link %s"%getEmoji(':mega:'))],
				[KeyboardButton("Rank %s"%getEmoji(':fire:'))],
				[KeyboardButton("Info %s"%getEmoji(':bulb:'))]
		]
		reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard = False, resize_keyboard = True)
		try:
			output = BOT.send_message(update.message.new_chat_members[0].id, text, reply_markup = reply_markup,  parse_mode=telegram.ParseMode.MARKDOWN, timeout=30)
		except(telegram.error.Unauthorized):
			logging.debug("Rejoin member message couldn't reach user because bot was already blocked.")
	# else: #se usuario entrou no grupo sem registro
		# if WELCOME_MSG:
			# text = "_%s Hello and welcome to the Adult X Token (ADUX) group community %s. %s_"%(getEmoji(':bulb:'), update.message.new_chat_members[0].first_name, WELCOME_MSG_TEXT)
			# bot.send_message(update.message.chat_id, text, parse_mode=telegram.ParseMode.MARKDOWN, timeout=30) 

def rejoinMemberChannel(userid):
	query("insert into channel_users (userid) values (%d) on conflict do nothing"%userid)
	if query("select count(*) from registered_users where userid =%d"%userid): #se usuario entrou no canal e tinha registro
		query("update registered_users set inside_channel = TRUE where userid =%d"%(userid))
		query("update statistics set left_channel_registered = left_channel_registered-1")
		text = "_%s You made the right choice. Be welcome to our channel again._"%(getEmoji(':white_check_mark:'))
		keyboard = [
					[KeyboardButton("Balance %s"%getEmoji(':moneybag:'))],
					[KeyboardButton("Referral link %s"%getEmoji(':mega:'))],
					[KeyboardButton("Rank %s"%getEmoji(':fire:'))],
					[KeyboardButton("Info %s"%getEmoji(':bulb:'))]
			]
		reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard = False, resize_keyboard = True)
		try:
			output = BOT.send_message(userid, text, reply_markup = reply_markup,  parse_mode=telegram.ParseMode.MARKDOWN, timeout=30)
		except(telegram.error.Unauthorized):
			logging.debug("Rejoin member message couldn't reach user because bot was already blocked.")
	else: #se usuario entrou no canal sem registro
		pass

@run_async
def leftMemberGroup(userid):
	query("delete from group_users where userid = %d"%userid)
	if query("select count(*) from registered_users where userid =%d"%userid): #se usuario que saiu do grupo tinha registro
		query("update registered_users set inside_group = FALSE where userid =%d"%userid)
		query("update statistics set left_group_registered = left_group_registered+1")
	else: #saiu sem registrar
		query("update statistics set left_group_not_registered = left_group_not_registered+1")
	keyboard = [[InlineKeyboardButton("Rejoin the group %s"%(getEmoji(':loudspeaker:')),url=CHAN['group']['link'])],]
	text = "_It seems you have left the group. \n\n%s IMPORTANT NOTE: you wont be able to receive your tokens at the end of this bounty! \n\nRejoin it for normalization._"%(getEmoji(':warning:'))
	reply_markup = InlineKeyboardMarkup(keyboard)
	try:
		output = BOT.send_message(userid, text, reply_markup = reply_markup,  parse_mode=telegram.ParseMode.MARKDOWN, timeout=30)
	except(telegram.error.Unauthorized):
		logging.debug("Left member message couldn't reach user because bot was already blocked.")

def leftMemberChannel(userid):
	query("delete from channel_users where userid = %d"%userid)
	if query("select count(*) from registered_users where userid =%d"%userid): #se usuario que saiu do canal e tinha registro
		query("update registered_users set inside_channel = FALSE where userid =%d"%(userid))
		query("update statistics set left_channel_registered = left_channel_registered+1")
	else: #saiu sem registrar
		query("update statistics set left_channel_not_registered = left_channel_not_registered+1")
	keyboard = [[InlineKeyboardButton("Rejoin the channel %s"%(getEmoji(':loudspeaker:')),url=CHAN['channel']['link'])],]
	text = "_It seems you have left the channel. \n\n%s IMPORTANT NOTE: you wont be able to receive your tokens at the end of this bounty! \n\nRejoin it for normalization._"%(getEmoji(':warning:'))
	reply_markup = InlineKeyboardMarkup(keyboard)
	try:
		output = BOT.send_message(userid, text, reply_markup = reply_markup,  parse_mode=telegram.ParseMode.MARKDOWN, timeout=30)
	except(telegram.error.Unauthorized):
		logging.debug("Left member message couldn't reach user because bot was already blocked.")

def deletePreviousMsg(bot, userid, msg):
	if isinstance(msg, list):
		for x in msg:
			bot.delete_message(userid,x)
	else:
		bot.delete_message(userid,msg)
	return []

@run_async
def deleteMsg(bot, update):
	if ANTI_SPAM:
		try:
			bot.delete_message(update.message.chat_id,update.message.message_id)
		except(telegram.error.BadRequest):
			return
		else:
			bot.restrict_chat_member(update.message.chat_id, update.message.from_user.id, until_date=int(time.time())+(60*60), can_send_messages=False, can_send_media_messages=False, can_send_other_messages=False, can_add_web_page_previews=False)
			text = "%s _Removed msg from %s. Reason: external link, photo or prohibited words. 1 hour chat restriction was applied._"%(getEmoji(':mute:'), update.message.from_user.first_name)
			bot.send_message(update.message.chat_id, text, parse_mode=telegram.ParseMode.MARKDOWN, timeout=30)

@run_async
@restricted
def adminToolbox(bot, update):
	text = 'Admin toolbox home'
	keyboard = [
			# [KeyboardButton("%s Disable welcome msg %s"%(getEmoji(':white_check_mark:'),getEmoji(':mute:')) if WELCOME_MSG else"%s Enable welcome msg %s"%(getEmoji(':ballot_box_with_check:'),getEmoji(':sound:'))),KeyboardButton("Edit welcome msg %s"%getEmoji(':pencil2:'))],
			# [KeyboardButton("%s Disable anti-spam %s"%(getEmoji(':white_check_mark:'),getEmoji(':sound:')) if ANTI_SPAM else"%s Enable anti-spam %s"%(getEmoji(':ballot_box_with_check:'),getEmoji(':mute:'))),KeyboardButton("Edit retweet link %s"%getEmoji(':pencil2:'))],
			[KeyboardButton("Edit retweet link %s"%getEmoji(':pencil2:'))],
			[KeyboardButton("Airdrop info %s"%getEmoji(':information_source:'))],
			[KeyboardButton("End airdrop %s"%(getEmoji(':no_entry:') if not END_AIRDROP else "Restart airdrop %s"%getEmoji(':recycle:')))],
			[KeyboardButton("Exit %s"%getEmoji(':x:'))]
	]
	botReplyKeyboard(update, text, keyboard, one_time_keyboard=False)
	return ADMIN_MENU

@restricted
def endAirdrop(bot, update):
	global END_AIRDROP
	if "Restart " in update.message.text:
		END_AIRDROP = False
		query('update config set end_airdrop = False')
		text = 'Airdrop/bounty sucefully restarted. %s'%getEmoji(':white_check_mark:')
		update.message.reply_text(text, timeout=30)
		adminToolbox(bot, update)
		return ADMIN_MENU
	else:
		text = '%s Do you really want to end this airdrop?\n\nWrite "end" to continue.'%getEmoji(':no_entry_sign:')
		update.message.reply_text(text, timeout=30)
		return END_AIRDROP_STATE

#END_AIRDROP_STATE
@restricted
def getEndAirdropResponse(bot, update):
	global END_AIRDROP
	if update.message.text == 'end':
		END_AIRDROP = True
		query('update config set end_airdrop = True')
		text = 'Airdrop/bounty sucefully ended. %s'%getEmoji(':white_check_mark:')
		update.message.reply_text(text, timeout=30)
	adminToolbox(bot, update)
	return ADMIN_MENU

# @restricted
# def toggleWelcomeMsg(bot, update):
# 	global WELCOME_MSG
# 	if re.search("Disable (.*)", update.message.text):
# 		WELCOME_MSG = False
# 		regex = re.search("Disable (.*)", update.message.text)
# 		text = '%s sucefully disabled!'%regex.group(1)
# 	elif re.search("Enable (.*)", update.message.text):
# 		WELCOME_MSG = True
# 		regex = re.search("Enable (.*)", update.message.text)
# 		text = '%s sucefully enabled!\n\nCurrent welcome message:\n\n%s'%(regex.group(1),WELCOME_MSG_TEXT)
# 	query("update config set welcome_msg_state = %s"%(str(WELCOME_MSG)))
# 	adminToolbox(bot, update)
# 	return ADMIN_MENU

# @restricted
# def toggleAntispam(bot, update):
# 	global ANTI_SPAM
# 	if re.search("Disable (.*)", update.message.text):
# 		regex = re.search("Disable (.*)", update.message.text)
# 		text = '%s sucefully disabled!'%regex.group(1)
# 		ANTI_SPAM = False
# 	elif re.search("Enable (.*)", update.message.text):
# 		ANTI_SPAM = True
# 		regex = re.search("Enable (.*)", update.message.text)
# 		text = '%s sucefully enabled!\n\n>> No links\n>> No photos\n>> No forwarded messages'%regex.group(1)
# 	query("update config set anti_spam_state = %s"%('true' if ANTI_SPAM else 'false'))
# 	adminToolbox(bot, update)
# 	return ADMIN_MENU

# @restricted
# def editWelcomeMsg(bot, update):
# 	text = 'Current welcome message:\n%s\n\nSend the new welcome text:'%WELCOME_MSG_TEXT
# 	keyboard = [[KeyboardButton("Home %s"%getEmoji(':house:'))],]
# 	botReplyKeyboard(update, text, keyboard, one_time_keyboard=True)
# 	return GET_WELCOME_TEXT

@restricted
def editRetweetLink(bot, update):
	text = 'Current retweet link:\n\n%s\n\nSend the new retweet link:'%RETWEET_LINK
	keyboard = [[KeyboardButton("Home %s"%getEmoji(':house:'))],]
	botReplyKeyboard(update, text, keyboard, one_time_keyboard=True, parse_mode=None)
	return GET_RETWEET_LINK

#GET_RETWEET_LINK
@run_async
def getRetweetLink(bot, update):
	if "Home " in update.message.text:
		adminToolbox(bot, update)
		return ADMIN_MENU
	elif not "'" in update.message.text:
		global RETWEET_LINK
		RETWEET_LINK = update.message.text
		text  = 'Retweet link sucefully changed! %s'%getEmoji(':white_check_mark:')
		query("update config set retweet_link = '%s'"%update.message.text)
		bot.send_message(update.message.chat_id, text, timeout=30)
		adminToolbox(bot, update)
		return ADMIN_MENU
	else:
		text = "Invalid retweet link. Please, send another:"
		keyboard = [[KeyboardButton("Home %s"%getEmoji(':house:'))],]
		botReplyKeyboard(update, text, keyboard, one_time_keyboard=True, parse_mode=None)
		return GET_RETWEET_LINK

# #GET_WELCOME_TEXT
# @run_async
# def getWelcomeText(bot, update):
# 	if "Home " in update.message.text:
# 		adminToolbox(bot, update)
# 		return ADMIN_MENU
# 	global WELCOME_MSG_TEXT
# 	WELCOME_MSG_TEXT = update.message.text
# 	query("update config set welcome_msg_text = '%s'"%update.message.text)
# 	text  = 'Welcome message sucefully changed! %s'%getEmoji(':white_check_mark:')
# 	bot.send_message(update.message.chat_id, text, timeout=30)
# 	adminToolbox(bot, update)
# 	return ADMIN_MENU

@run_async
@restricted
def adminInfo(bot, update):
	registered_users_qtd = query('select count(*) from registered_users') or 0
	affiliates_qtd = query ('select sum(affiliates) from registered_users') or 0
	hourly_registrations = query ("select date_part('hour', joindate) as hour,count(*) as qtd from registered_users group by hour order by hour") or 0
	hourly_registrations_avg = query ("select avg(b.qtd) from (select date_part('month', joindate) as month,date_part('day', joindate) as day, date_part('hour', joindate) as hour,count(*) as qtd from registered_users group by month,day,hour) b") or 0
	daily_registrations_avg = query ("select avg(b.qtd) from (select date_part('month', joindate) as month,date_part('day', joindate) as day, count(*) as qtd from registered_users group by month,day) b") or 0
	# total_twitter = query ("select count(*) from registered_users where twitter != ''")
	# total_instagram = query ("select count(*) from registered_users where instagram != ''")
	# total_medium = query ("select count(*) from registered_users where medium != ''")
	# total_reddit = query ("select count(*) from registered_users where reddit != ''")
	total_claimed = affiliates_qtd*CONFIG.REFERRAL_TOKEN_VALUE+registered_users_qtd*CONFIG.JOIN_TOKEN_VALUE
	# total_claimed += (total_twitter+total_instagram+total_medium+total_reddit)*CONFIG.SOCIALMEDIA_TOKEN_VALUE
	text = '''Total registered users: `{:,d}`
Total claimed tokens: `{:,d}`
Registrations per hour rate: `{:,.1f}`
Registrations per day rate: `{:,.1f}`'''.format(registered_users_qtd, 
																		total_claimed, 
																		hourly_registrations_avg,
																		daily_registrations_avg
						)
	keyboard = [
			# [KeyboardButton("Plot Registrations %s"%getEmoji(':clipboard:'))],
			[KeyboardButton("Full log .csv %s"%getEmoji(':clipboard:'))],
			[KeyboardButton("Home %s"%getEmoji(':house:'))],
	]
	botReplyKeyboard(update, text, keyboard, one_time_keyboard=False)

@run_async
@restricted
def getLog(bot, update):
	query("COPY registered_users TO  '%s/registered_users_log.csv' CSV HEADER DELIMITER ',' "%os.path.dirname(os.path.abspath(__file__)))
	bot.send_document(chat_id=update.message.chat_id, document=open(os.path.dirname(os.path.abspath(__file__))+'/registered_users_log.csv', 'rb'), timeout=100)


def setChannels():
	# channels = [{'name','username'},...,]
	global CHAN
	for x in ['GROUP', 'CHANNEL', 'BOT']:
		username = CONFIG['TELEGRAM_'+x]
		group_dict = {
				'name': x.lower(),
				'username':username, 
				'link':'https://t.me/%s'%username.lstrip('@'),
				'share':'https://t.me/share/url?url=https://t.me/%s'%username.lstrip('@')
		}
		CHAN[x.lower()] = group_dict

def startClient():
	CLIENT.connect()
	if not CLIENT.is_user_authorized():
		CLIENT.send_code_request(CONFIG.CLIENT_PHONE)
		CLIENT.sign_in(CONFIG.CLIENT_PHONE, input('Enter code: '))

def startTwitter():
	global TWITTER_APPS
	out = query('select name,consumer_key,consumer_secret,token,token_secret from twitter_apps' )
	for (name,consumer_key,consumer_secret,token,token_secret) in out:
		# TWITTER_APPS = [dot({'name':name, 'consumer_key':consumer_key, 'consumer_secret':consumer_secret,'token':token,'token_secret':token_secret}) for (name,consumer_key,consumer_secret,token,token_secret) in out]
		auth = tweepy.OAuthHandler(consumer_key,consumer_secret)
		auth.set_access_token(token,token_secret)
		app = tweepy.API(auth, wait_on_rate_limit=False, wait_on_rate_limit_notify=True, compression=True)
		TWITTER_APPS.append(app)

def getTwitterApp():
	TW_LOCK.acquire()
	app = TWITTER_APPS.pop(0)
	TWITTER_APPS.append(app)
	TW_LOCK.release()
	return app

def receiveFile(bot, update):
 	# logging.warning(update.message.photo.file_id)
 	logging.warning(update.to_dict())

def echoMsg(bot, update):
	logging.warning(update.message.text)
	logging.warning(update.message.text.encode('utf-32'))
	logging.warning(update.message.text.encode('utf-8').decode('utf-32'))
	# logging.warning(update.message.text.encode('utf-32').decode('utf-8'))

def logginClient(bot, update):
	CLIENT.sign_in(CONFIG.CLIENT_PHONE, update.message.text)

class MQBot(telegram.bot.Bot):
	def __init__(self, *args, is_queued_def=True, msg_queue=None, **kwargs):
		super().__init__(*args, **kwargs)
		# For decorator usage
		self._is_messages_queued_default = is_queued_def
		self._msg_queue = msg_queue or mqueue.MessageQueue()

	@mqueue.queuedmessage
	def send_message(self, *args, **kwargs):
    		super().send_message(*args, **kwargs)

@run_async
def makeCaptchas(bot, update):
	print(update.message.text.encode('utf-32').decode('utf-8'))
	f = open('telegram_emoji_string.txt', 'r')
	emojis = [(x.encode('utf-8').decode('unicode-escape'), x) for x in f.readlines()[0].split(';')]
	f.close()
	for emoji,unicode_string in emojis[:2]:
		print(emoji, unicode_string)
		image = Image.new("RGBA", (60,60), (0,0,0))
		font = ImageFont.truetype("Symbola.ttf", 60, encoding='unic')
		draw = ImageDraw.Draw(image)
		draw.text((0,0), emoji, (255,255,255), font=font)
		image.save("./captchas/"+unicode_string.lstrip('\\')+".png")
		try:
			msg = BOT.send_photo(update.message.chat.id, open('./captchas/'+unicode_string.lstrip('\\')+'.png', 'rb'))
		except Exception as e:
			logging.warning(e)
		else:
			query("insert into captchas (unicode_string, file_id) values ('%s', '%s') on conflict (unicode_string) do nothing"%(unicode_string, msg.photo[0].file_id))
			sleep(0.31)


#----------------------------------------------------------------------------------------------------#
# INITIALIZING                                                         	     
#----------------------------------------------------------------------------------------------------#
loadConfig()
DB = connectPSQL()
DB_LOCK = threading.Lock()
TW_LOCK = threading.Lock()
CLIENT = TelegramClient(os.path.dirname(os.path.abspath(__file__))+'/client.session', CONFIG.CLIENT_ID, CONFIG.CLIENT_HASH)
BOT = MQBot(CONFIG.BOT_TOKEN, request=telegram.utils.request.Request(con_pool_size=8), msg_queue=mqueue.MessageQueue(all_burst_limit=29, all_time_limit_ms=1017))
# WELCOME_MSG_TEXT = query("select welcome_msg_text from config")
# WELCOME_MSG = query("select welcome_msg_state from config")
# ANTI_SPAM = query("select anti_spam_state from config")
RETWEET_LINK = query("select retweet_link from config")
END_AIRDROP = query("select end_airdrop from config")
TWITTER_APPS = []

def main():
	updater = Updater(CONFIG.BOT_TOKEN)
	# add handlers
	updater.start_webhook(	listen="127.0.0.1",
					port=CONFIG.INTERNAL_PORT,
					url_path=CONFIG.BOT_TOKEN,
					)
	try:
		updater.bot.setWebhook(	url = "https://%s:%d/%s"%(CONFIG.HOST, CONFIG.PORT,CONFIG.BOT_TOKEN),
					certificate=open(CONFIG.CERT, 'rb')
					)
	except:
		pass
	# updater.dispatcher.add_handler(CommandHandler('test', echoMsg, filters=Filters.private))
	# updater.dispatcher.add_handler(MessageHandler(Filters.private|Filters.document, receiveFile))
	updater.dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, joinMemberGroup))
	updater.dispatcher.add_handler(MessageHandler(Filters.status_update.left_chat_member, leftMemberGroup))
	# updater.dispatcher.add_handler(RegexHandler('make captchas', makeCaptchas))
	updater.dispatcher.add_handler(RegexHandler('(?i)^\/?Balance', echoBalance))
	updater.dispatcher.add_handler(RegexHandler('(?i)^\/?Balance', echoBalance))
	# updater.dispatcher.add_handler(RegexHandler('(?i).*(s.*c.*a.*m|f.*a.*k.*e).*', deleteMsg))
	# updater.dispatcher.add_handler(MessageHandler((Filters.group & (Filters.photo | Filters.video | (Filters.entity('url') | Filters.entity('text_link')) | Filters.forwarded)), deleteMsg))
	updater.dispatcher.add_handler(RegexHandler('(?i)^\/?Info', echoInfo))
	updater.dispatcher.add_handler(RegexHandler('(?i)^\/?Rank', echoRank))
	updater.dispatcher.add_handler(RegexHandler('(?i)^Referral', echoReferralLink))
	# updater.dispatcher.add_handler(MessageHandler(Filters.private|Filters.document, receiveFile))
	updater.dispatcher.add_handler(ConversationHandler(
										entry_points=[CommandHandler('toolbox', adminToolbox, Filters.private)],
										states = {
												ADMIN_MENU: [	
															# RegexHandler('.*able welcome msg.*', toggleWelcomeMsg),
															# RegexHandler('.*able anti-spam.*', toggleAntispam),
															RegexHandler('^Edit retweet link.*', editRetweetLink),
															# RegexHandler('^Edit welcome msg.*', editWelcomeMsg),
															RegexHandler('^Airdrop info', adminInfo),
															RegexHandler('^(End|Restart) airdrop.*', endAirdrop)
												],
												# GET_WELCOME_TEXT: [MessageHandler(Filters.private, getWelcomeText)],
												GET_RETWEET_LINK: [MessageHandler(Filters.entity('url'), getRetweetLink)],
												END_AIRDROP_STATE:[MessageHandler(Filters.private, getEndAirdropResponse)]
										},
										allow_reentry=True,
										fallbacks = [	RegexHandler('^Exit ', cancel),
												RegexHandler('^Home ', adminToolbox),
												RegexHandler('^Full log \.csv', getLog)
										]
									)
						)
	updater.dispatcher.add_handler(ConversationHandler(
														entry_points=[	CommandHandler('start', botCheck, filters=Filters.private, pass_user_data=True),
																	CallbackQueryHandler(groupJoinCheck, pattern='^\d+$', pass_user_data=True)
														],
														states = {	
																	BOT_CHECK: [MessageHandler(Filters.private, botCheck,  pass_user_data=True)],
																	GROUP_JOIN_CHECK: [CallbackQueryHandler(groupJoinCheck, pattern='^\d+$', pass_user_data=True)],
																	# EMAIL :[MessageHandler(Filters.private, getEmail, pass_user_data=True)],
																	WALLET: [MessageHandler(Filters.private, getWallet, pass_user_data=True)],
																	TWITTER :[MessageHandler(Filters.private, getTwitter, pass_user_data=True)],
																	# FACEBOOK :[MessageHandler(Filters.private, getFacebook, pass_user_data=True)],
																	# REDDIT :[MessageHandler(Filters.private, getReddit, pass_user_data=True)],
																	# INSTAGRAM :[MessageHandler(Filters.private, getInstagram, pass_user_data=True)],
																	# MEDIUM :[MessageHandler(Filters.private, getMedium, pass_user_data=True)],
																	# CONFIRM_EMAIL :[MessageHandler(Filters.private, confirmEmail, pass_user_data=True)],
																	CONFIRM_WALLET: [MessageHandler(Filters.private, confirmWallet, pass_user_data=True)],
																	# CONFIRM_FACEBOOK :[MessageHandler(Filters.private, confirmFacebook, pass_user_data=True)],
																	# CONFIRM_REDDIT :[MessageHandler(Filters.private, confirmReddit, pass_user_data=True)],
																	# CONFIRM_INSTAGRAM:[MessageHandler(Filters.private, confirmInstagram, pass_user_data=True)],
																	# CONFIRM_MEDIUM :[MessageHandler(Filters.private, confirmMedium, pass_user_data=True)],
														},
														fallbacks = [RegexHandler('(?i)^\/?Exit ', cancel)],
														allow_reentry =True
														)
									)	
	startClient()
	setChannels()
	startTwitter()
	threading.Thread(target=updateDatabase,args=()).start()
	CLIENT.run_until_disconnected()
	updater.idle()

if __name__ == '__main__':
    main()
