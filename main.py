#!/usr/bin/env python

import logging
from typing import Dict

from telegram import __version__ as TG_VER

try:
    from telegram import __version_info__
except ImportError:
    __version_info__ = (0, 0, 0, 0, 0)  # type: ignore[assignment]

if __version_info__ < (20, 0, 0, "alpha", 1):
    raise RuntimeError(
        f"This example is not compatible with your current PTB version {TG_VER}. To view the "
        f"{TG_VER} version of this example, "
        f"visit https://docs.python-telegram-bot.org/en/v{TG_VER}/examples.html"
    )
from telegram import ReplyKeyboardMarkup, Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PicklePersistence,
    filters,
    CallbackQueryHandler
)
from telegram.constants import ParseMode
from typing import Final
import psutil
import subprocess
import aiofiles 
import asyncio
import os
from functools import wraps

from config import valheimlog, server_proc_name, server_base_dir

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
threads=[]
online=[]
status=''
kbdConfirm = [
        [InlineKeyboardButton(text="Terminate",callback_data="Terminate")]
    ]
kbd = [
        [InlineKeyboardButton(text="Run Modded",callback_data="RunModded")],
        [InlineKeyboardButton(text="Run Vanilla",callback_data="RunVanilla")],
        [InlineKeyboardButton(text="Status",callback_data="Status")],
        [InlineKeyboardButton(text="Stop",callback_data="Stop")],
        [InlineKeyboardButton(text="Online",callback_data="Online")],
        [InlineKeyboardButton(text="Button",callback_data="Button")]
    ]
kbdDesktop = [
        [InlineKeyboardButton(text="Run Modded",callback_data="RunModded"),InlineKeyboardButton(text="Run Vanilla",callback_data="RunVanilla")],
        [InlineKeyboardButton(text="Status",callback_data="Status"),InlineKeyboardButton(text="Online",callback_data="Online")],
        [InlineKeyboardButton(text="Stop",callback_data="Stop")],
        
    ]
KbdConfirmMarkupInline = InlineKeyboardMarkup(kbdConfirm)
ControlPanelMarkupReply = ReplyKeyboardMarkup(kbd)
ControlPanelMarkupReplyDesktop = ReplyKeyboardMarkup(kbdDesktop)
TOKEN:Final = os.environ.get('TOKEN')
ADMINIDS:Final = os.environ.get('ADMINIDS')

print(f'TOKEN={TOKEN} and ADMINIDS={ADMINIDS}')
if(not (TOKEN and ADMINIDS)):
    print('Both TOKEN and ADMINIDS is necessary to run the bot. Supply them as environment variable and start the bot.')
    exit(1)
# WRAPPERS    
#wrapper for admin functions
def restricted(func):
    @wraps(func)
    async def wrapped(update, context, *args, **kwargs):
        user_id = str(update.effective_user.id)
        if user_id not in ADMINIDS:
            print(f"Unauthorized access denied for {user_id}.")
            await context.bot.send_message(chat_id = user_id, text="You are not allowed to use admin functions.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

#get process PID by name 
# for Valheim default is "./valheim_server.x86_64" 
def find_server_process(procname)->psutil.Process:
    processes = psutil.process_iter()
    for process in processes:
        if procname in process.cmdline():
            return(process.pid)
    return 0

#GENERAL COMMAND HANDLERS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if str(update.effective_user.id) in ADMINIDS:
        reply_text = 'Hello, Admin!\nWelcome to Valheim Dedicated Server Control Bot\n/control gives you server control panel.'
    reply_text = 'Hello, user!\nWelcome to Valheim Dedicated Server Control Bot\n/control gives you server control panel.'
    await update.message.reply_text(reply_text,reply_markup=ControlPanelMarkupReply)  
    
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # context.user_data.clear()
    # current_jobs = context.job_queue.get_jobs_by_name(context._user_id)
    # for job in current_jobs:
    #     job.schedule_removal()
    await update.message.reply_text('Control panel removed\n/start to get it again.',reply_markup=ReplyKeyboardRemove())
    
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text =  'List of commands, those marked with an asterisk require admin rights:' \
        '\n/control gives you server control panel' \
        '\n*/run starts the server' \
        '\n*/stop stops the server' \
        '\n/status gives you current status of server, if it starting, stopping and etc.' \
        '\n/online shows who online' \
        '\n/sw_layout switches server control panel layout to mobile or desktop' \
        '\n/cancel removes control panel'
    await update.message.reply_text(text)

#function sends control inline keyboard
async def send_control_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    layout = context.user_data.get('layout')
    if not layout:
        context.user_data["layout"] = 'mobile'
        layout = 'mobile'
    if layout == 'mobile':
        markup = ControlPanelMarkupReply
    if layout == 'desktop':
        markup = ControlPanelMarkupReplyDesktop

    await context.bot.send_message(chat_id = context._user_id, text='Control panel', reply_markup=markup)
    return 0

#switch control panel's layout
async def switch_layout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    layout = context.user_data.get('layout')
    if layout == 'mobile':
        context.user_data["layout"] = 'desktop'
    if layout == 'desktop':
        context.user_data["layout"] = 'mobile'
    await send_control_panel(update, context)
    
#SERVER MANAGEMENT FUNCTIONS
#TODO:RESTART
@restricted
async def request_server_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answers={
        0:'Shutdown process initiated',
        1:'Server has already stopped',
        2:'The server shutdown has already been initiated'
    }
    # await context.bot.send_message(chat_id = context._user_id, text="Let's stop the server")
    result=answers.get(server_stop())
    await context.bot.send_message(chat_id = context._user_id, text=result)

def server_stop() -> int:
    global status
    if status == 'Stopping':
        print('The server shutdown has already been initiated. Please wait.')
        return 2
    pid = find_server_process(server_proc_name)
    if(pid):
        # Gracefully stop valheim server
        status = 'Stopping'
        print(f"Servers's PID is {pid}")
        psutil.Process(pid).send_signal(2)
        return 0
    else:
        print('Server has already stopped')
        return 1
    
@restricted
async def request_server_run_modded(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answers={
        0:'Starting process initiated',
        1:'Server is running',
        2:'The server start has already been initiated'
    }
    # await context.bot.send_message(chat_id = context._user_id, text="Let's start the server")
    result=answers.get(server_run_modded())
    await context.bot.send_message(chat_id = context._user_id, text=result)

def server_run_modded() -> int:
    global status
    print('Try to start Modded server')
    if(find_server_process(server_proc_name)):
        print('Server running')
        return 1
    else:
        # starting server from it's working directory and change it back to bot current working directory afterwards
        print('Trying to start Modded server')
        cwd = os.getcwd()
        os.chdir(server_base_dir)
        subprocess.Popen(["bash","/valheimds/start-bepinex-valheim.sh"])
        print('Modded server start initiated')
        os.chdir(cwd)
        status = 'Starting'
        return 0

@restricted
async def request_server_run_vanilla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answers={
        0:'Starting process initiated',
        1:'Server is running',
        2:'The server start has already been initiated'
    }
    # await context.bot.send_message(chat_id = context._user_id, text="Let's start the server")
    result=answers.get(server_run_vanilla())
    await context.bot.send_message(chat_id = context._user_id, text=result)

def server_run_vanilla() -> int:
    global status
    print('Try to start vanilla server')
    if(find_server_process(server_proc_name)):
        print('Server running')
        return 1
    else:
        # starting server from it's working directory and change it back to bot current working directory afterwards
        print('Trying to start vanilla server')
        cwd = os.getcwd()
        os.chdir(server_base_dir)
        subprocess.Popen(["bash","/valheimds/start-valheim.sh"])
        print('Vanailla Server start initiated')
        os.chdir(cwd)
        status = 'Starting'
        return 0

async def request_server_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(chat_id = context._user_id, text=server_status())

def server_status() -> str:
    return(f"Server status:{status}\nServer process PID {find_server_process(server_proc_name)}")

async def request_server_online(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(chat_id = context._user_id, text=server_online())

def server_online() -> str:
    #TODO: list online players with names
    return(f"Status: {status}\nOnline: {len(online)} people")

@restricted
async def request_server_terminate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    term_msg = await context.bot.send_message(
        reply_markup=KbdConfirmMarkupInline,
        chat_id= context._user_id,
        text='Are you sure want to terminate server? ' \
              'It may cause problem such as currupted save file and even ruin world completely.' \
              'This message will dissapear in 5 seconds.'
        )
    context.job_queue.run_once(callback=delete_message,when=5,chat_id=term_msg.chat_id,data=term_msg.message_id)

async def delete_message(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.delete_message(chat_id=job.chat_id, message_id=job.data)

async def server_terminate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    global status
    pid = find_server_process(server_proc_name)
    if(pid):
        # Force termination of the valheim server
        status = 'Terminating'
        print(f"Servers's PID is {pid}. Terminating")
        await context.bot.send_message(chat_id=context._user_id, text=f"Servers's PID is {pid}. Terminating")
        psutil.Process(pid).send_signal(15)
        return 0
    else:
        print("Server's process wasn't found")
        await context.bot.send_message(chat_id=context._user_id, text="Server's process wasn't found")
        return 1

async def process_control_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command = update.message.text
    # await query.answer()
    # await context.bot.send_message(chat_id = context._user_id, text=f'Processing command {query.data}')
    if command == 'Status':
        #await context.bot.send_message(chat_id = context._user_id, text=request_server_status())
        await request_server_status(update, context)
    if command == 'Run Modded':
        # await context.bot.send_message(chat_id = context._user_id, text=request_server_run(update, context))
        await request_server_run_modded(update, context)
    if command == 'Run Vanilla':
        # await context.bot.send_message(chat_id = context._user_id, text=request_server_run(update, context))
        await request_server_run_vanilla(update, context)
    if command == 'Stop':
        # await context.bot.send_message(chat_id = context._user_id, text=request_server_stop(update, context))
        await request_server_stop(update, context)
    if command == 'Online':
        # await context.bot.send_message(chat_id = context._user_id, text=request_server_online())
        await request_server_online(update, context)
    if command == 'Button':
        await request_server_online(update, context)
    
async def keep_reading_logfile():    
    while True:
        await parse_server_output()

async def parse_server_output():
    global status
    global online
    # print('in log parser func')
    fsize = os.path.getsize(valheimlog)
    async with aiofiles.open(valheimlog, mode='rb') as f:
        print(f'open file {valheimlog}')
        while True:
            await asyncio.sleep(0)
            line = await f.readline()
            if(not line):
                #print('wait')
                await asyncio.sleep(0.1)
                if fsize > os.path.getsize(valheimlog):
                    print('Reopening file')
                    break
            else:
                line = str(line)
                # print(line)
                if 'Got handshake from client' in line:
                    steamid = line.split()[-1]
                    if steamid not in online:
                        online.append(steamid)
                        print(f'CONNECTION DETECTED {steamid}')
                if 'Closing socket' in line:
                    steamid = line.split()[-1]
                    if steamid in online:
                        online.remove(steamid)
                        print(f'USER DISCONNECTED {steamid}')
                if 'Shuting down' in line:
                    status = 'Stopping'
                    print(f'SERVER STARTED SHUT DOWN AT {line.split(" ",2)[1]}')
                if 'Net scene destroyed' in line:
                    status = 'Stopped'
                    online.clear()
                    print(f'SERVER SHUT DOWN COMPLETELY AT {line.split(" ",2)[1]}')
                if 'Mono config path' in line:
                    status = 'Starting'
                    print(f'SERVER STARTING')
                if 'Game server connected' in line:
                    status = 'Online'
                    print(f'SERVER ONLINE')

async def main():
    #Application setup
    # Create the Application and pass it your bot's token.
    persistence = PicklePersistence(filepath="status_cache")
    application = Application.builder().token(TOKEN).persistence(persistence).build()

    application.add_handler(MessageHandler(filters.Regex("^(Status|Run Modded|Run Vanilla|Stop|Online|Button)$"), process_control_panel))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, help))

    #callbackquery handlers
    #terminate button handler
    handler = CallbackQueryHandler(server_terminate, pattern="^Terminate$")
    application.add_handler(handler)

    # application.add_handler(CallbackQueryHandler(process_control_panel))

    #General purpose commands
    handler = CommandHandler("start", start)
    application.add_handler(handler)
    handler = CommandHandler("cancel", cancel)
    application.add_handler(handler)
    handler = CommandHandler("help", help)
    application.add_handler(handler)
    handler = CommandHandler("control", send_control_panel)
    application.add_handler(handler)
    handler = CommandHandler("sw_layout", switch_layout)
    application.add_handler(handler)
    #Valheim server coomands
    handler = CommandHandler("status", request_server_status)
    application.add_handler(handler)
    handler = CommandHandler("runmodded", request_server_run_modded)
    application.add_handler(handler)
    handler = CommandHandler("runvanilla", request_server_run_vanilla)
    application.add_handler(handler)
    handler = CommandHandler("stop", request_server_stop)
    application.add_handler(handler)
    handler = CommandHandler("online", request_server_online)
    application.add_handler(handler)
    handler = CommandHandler("terminate", request_server_terminate)
    application.add_handler(handler)


    async with application: 
        print('----1-----')
        await application.initialize()
        print('----2-----')
        await application.start()
        print('----3-----')
        await application.updater.start_polling()
        print('----4-----')
        await keep_reading_logfile()
        print('----5-----')
        await application.updater.stop()
        print('----6-----')
        await application.stop()
        print('----7-----')

if __name__ == "__main__":
    asyncio.run(main())
    #main()