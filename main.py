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
import re
import threading
import aiofiles 
import asyncio
import os
import datetime
from functools import wraps

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
kbd = [
        [InlineKeyboardButton(text="Run",callback_data="Run")],
        [InlineKeyboardButton(text="Status",callback_data="Status")],
        [InlineKeyboardButton(text="Stop",callback_data="Stop")],
        [InlineKeyboardButton(text="Online",callback_data="Online")],
        [InlineKeyboardButton(text="Button",callback_data="Button")]
    ]
ControlPanelMarkup = InlineKeyboardMarkup(kbd)

TOKEN:Final = os.environ.get('TOKEN')
ADMINIDS:Final = os.environ.get('ADMINIDS')
# valheimlog = '/mnt/e/projects/bots/tgvhctl/valheimds.log'
valheimlog = '/valheimds/valheimds.log'
server_proc_name = "./valheim_server.x86_64"
server_base_dir = '/valheimds/'
# valheimlog = '/mnt/e/projects/bots/tgvhctl/valheimds2.log'
print(f'TOKEN={TOKEN} and ADMINIDS={ADMINIDS}')
if(not (TOKEN and ADMINIDS)):
    print('Both TOKEN and ADMINIDS is necessary to run the bot. Supply them as environment variable and start the bot.')
    exit(1)
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
    await update.message.reply_text(reply_text)  
    
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    current_jobs = context.job_queue.get_jobs_by_name(context._user_id)
    for job in current_jobs:
        job.schedule_removal()
    await update.message.reply_text('Cache clearead.\n/start to start again.')
    
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text =  'List of commands, those marked with an asterisk require admin rights:' \
        '\n/control gives you server control panel' \
        '\n*/run starts the server' \
        '\n*/stop stops the server' \
        '\n/status gives you current status of server, if it starting, stopping and etc.' \
        '\n/online shows who online'
    await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())

#function sends control inline keyboard
async def send_control_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await context.bot.send_message(
            chat_id = context._user_id, text='Control panel', reply_markup=ControlPanelMarkup
        )
    return 0

#SERVER MANAGEMENT FUNCTIONS
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
        # proc.send_signal()
        return 0
    else:
        print('Server has already stopped')
        return 1
    
@restricted
async def request_server_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    answers={
        0:'Starting process initiated',
        1:'Server is running',
        2:'The server start has already been initiated'
    }
    # await context.bot.send_message(chat_id = context._user_id, text="Let's start the server")
    result=answers.get(server_run())
    await context.bot.send_message(chat_id = context._user_id, text=result)

def server_run() -> int:
    print('Starting server')
    if(find_server_process(server_proc_name)):
        print('Server running')
        return 1
    else:
        print('Trying to start server')
        os.chdir(server_base_dir)
        subprocess.Popen(["bash","/valheimds/start-bepinex-valheim.sh"])
        print('Server start initiated')
        return 0

async def request_server_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # if str(update.effective_user.id) not in ADMINIDS:
    #     await context.bot.send_message(chat_id = context._user_id, text='Status user')
        
    # await context.bot.send_message(chat_id = context._user_id, text='Status admin')
    await context.bot.send_message(chat_id = context._user_id, text=server_status())

def server_status() -> str:
    return(f"Server status:{status}\nServer process PID {find_server_process(server_proc_name)}")

async def request_server_online(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(chat_id = context._user_id, text=server_online())

def server_online() -> str:
    return(f"Status: {status}\nOnline: {len(online)} people")

async def process_control_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # await context.bot.send_message(chat_id = context._user_id, text=f'Processing command {query.data}')
    if query.data == 'Status':
        #await context.bot.send_message(chat_id = context._user_id, text=request_server_status())
        await request_server_status(update, context)
    if query.data == 'Run':
        # await context.bot.send_message(chat_id = context._user_id, text=request_server_run(update, context))
        await request_server_run(update, context)
    if query.data == 'Stop':
        # await context.bot.send_message(chat_id = context._user_id, text=request_server_stop(update, context))
        await request_server_stop(update, context)
    if query.data == 'Online':
        # await context.bot.send_message(chat_id = context._user_id, text=request_server_online())
        await request_server_online(update, context)
    if query.data == 'Button':
        await request_server_online(update, context)
    #await query.message.edit_text(f'Pressed {query.data}')
    #await update.message.reply_text(f'Pressed {query.data}', reply_markup=ReplyKeyboardRemove())
    #reply_text(f'Pressed {query.data}', reply_markup=ReplyKeyboardRemove())
    #Separate thread for function which generates link
    #thread = threading.Thread(target=generate_url, args= (context,link,update.message.id,))
    #threads.append(thread)
    #thread.start()

    #context.job_queue.run_repeating(callback=server_status, interval=1, user_id=context._user_id)
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
                if 'Got image' in line:
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

    application.add_handler(
        MessageHandler(
        filters.TEXT & ~(filters.COMMAND | filters.Regex("^(Download|Cancel)$")), help
        )
    )
    application.add_handler(CallbackQueryHandler(process_control_panel))

    #General purpose commands
    start_handler = CommandHandler("start", start)
    application.add_handler(start_handler)
    cancel_handler = CommandHandler("cancel", cancel)
    application.add_handler(cancel_handler)
    help_handler = CommandHandler("help", help)
    application.add_handler(help_handler)
    help_handler = CommandHandler("control", send_control_panel)
    application.add_handler(help_handler)
    #Valheim server coomands
    help_handler = CommandHandler("status", server_status)
    application.add_handler(help_handler)
    help_handler = CommandHandler("run", server_run)
    application.add_handler(help_handler)
    help_handler = CommandHandler("stop", server_stop)
    application.add_handler(help_handler)
    help_handler = CommandHandler("online", server_online)
    application.add_handler(help_handler)

    async def keep_printing(name):
        while True:
            print(name, end=" ")
            print(datetime.datetime.now())
            await asyncio.sleep(0.5)
    

    #log_parser = parse_server_output()

    async with application: 
        print('----1-----')
        await application.initialize()
        print('----2-----')
        await application.start()
        print('----3-----')
        await application.updater.start_polling()
        print('----4-----')
        # await keep_printing('one')
        print('----5-----')
        await keep_reading_logfile()
        print('----55-----')
        await application.updater.stop()
        print('----6-----')
        await application.stop()
        print('----7-----')

if __name__ == "__main__":
    asyncio.run(main())
    #main()