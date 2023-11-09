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
from functools import partial
import psutil
import subprocess
import signal
import aiofiles 
import asyncio
import os
import contextlib
from functools import wraps

from config import * #valheimlog, server_proc_name, server_base_dir

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.WARNING
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
threads=[]
online={}
status='Stopped'                #game server status
last_connected = []

kbdConfirm = [
        [InlineKeyboardButton(text="kill",callback_data="kill")]
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

# serverprocess_task = asyncio.create_task(asyncio.create_subprocess_exec("echo", "init"))
# serverprocess = await serverprocess_task
#serverprocess = await asyncio.create_subprocess_exec("echo", "init")
TOKEN:Final = os.environ.get('TOKEN')
ADMINIDS:Final = os.environ.get('ADMINIDS')
DETACHED_PROCESS = 0x00000008


def preconditions():
    print(f'TOKEN={TOKEN} and ADMINIDS={ADMINIDS}')
    if(not (TOKEN and ADMINIDS)):
        # print('Both TOKEN and ADMINIDS is necessary to run the bot. Supply them as environment variables and start the bot.')
        logger.error('Both TOKEN and ADMINIDS is necessary to run the bot. Supply them as environment variables and start the bot.')
        exit(1)

    print(f'Current working directory: {server_base_dir}')
    
    if(not os.path.isfile(sh_path_vainlla)):
        # print('Vanilla run script ({sh_path_vainlla}) was not found. Ensure that it present in server directory')
        logger.warning(f'Vanilla run script ({sh_path_vainlla}) was not found. Ensure that it present in server directory')
    
    if(not os.path.isfile(sh_path_vainlla)):
        # print('Modded run script ({sh_path_modded}) was not found. Ensure that it present in server directory')
        logger.warning(f'Modded run script ({sh_path_modded}) was not found. Ensure that it present in server directory')
    

preconditions()
# WRAPPERS    
#wrapper for admin functions
def restricted(func):
    @wraps(func)
    async def wrapped(update, context, *args, **kwargs):
        user_id = str(update.effective_user.id)
        if user_id not in ADMINIDS:
            logger.warning(f"Unauthorized access denied for {user_id}.")
            await context.bot.send_message(chat_id = user_id, text="You are not allowed to use admin functions.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

#get process PID by name. Returns 0 if nothing found
# for Valheim default is VlheimMainThre 
def get_server_process(procname)->psutil.Process:
    processes = psutil.process_iter()
    for process in processes:
        if procname in process.name():
            return(process)
    return 0
#checks if process running 
async def is_running(proc):
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(proc.wait(), 1e-6)
    return proc.returncode is None

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
        1:'The server has already stopped',
        2:'The server shutdown has already been initiated'
    }
    # await context.bot.send_message(chat_id = context._user_id, text="Let's stop the server")
    result=answers.get(await server_stop())
    await context.bot.send_message(chat_id = context._user_id, text=result)

async def server_stop() -> int:
    global status
    
    # if status == 'Stopping':
    #     print('The server shutdown has already been initiated. Please wait.')
    #     return 2
    srv_process = get_server_process(server_proc_name)
    if(srv_process):
        # Gracefully stop valheim server
        print(f"Terminating server process with PID:{srv_process.pid}")
        srv_process.terminate()
        # status = 'Stopping'
        return 0
    else:
        print('The server has already stopped')
        return 1
    
@restricted
async def request_server_run(update: Update, context: ContextTypes.DEFAULT_TYPE, mode='vanilla') -> int:
    answers={
        0:f'{mode} server starting process initiated',
        1:f'{mode} server is running',
        2:f'{mode} server start has already been initiated'
    }
    # await context.bot.send_message(chat_id = context._user_id, text="Let's start the server")
    result=answers.get(await server_run(mode))
    await context.bot.send_message(chat_id = context._user_id, text=result)

async def server_run(mode) -> int:
    global status
    global serverprocess
    print(f'Try to start {mode} server')
    srv_process = get_server_process(server_proc_name)
    if(srv_process):
        print(f"Server process is running with PID: {srv_process.pid}")
        return 1
    else:
        # starting server from it's working directory and change it back to bot current working directory afterwards
        cwd = os.getcwd()
        os.chdir(server_base_dir)
        # status = 'Starting'
        serverprocess = await asyncio.create_subprocess_exec("nohup","bash",f"{server_base_dir}run-{mode}.sh",stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

        print(f'{mode} server start initiated')
        os.chdir(cwd)
        return 0

async def request_server_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(chat_id = context._user_id, text=await server_status())

async def server_status() -> str:    
    srv_process = get_server_process(server_proc_name)
    if(srv_process):
        result = f"Game server status: {status}\nServer process is runiing with PID: {srv_process.pid}"
    else:
        result = f"Game server status: Stopped (no pid)"
    return result

async def request_server_online(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(chat_id = context._user_id, text=server_online())

def server_online() -> str:
    #TODO: list online players with names
    if(len(online)):
        playerlist='Playerlist:\n'
        for key, value in online.items():
            playerlist+=f'{value}:{key}'
        return(f"Status: {status}\nOnline: {len(online)} people\n{playerlist}")
    else:
        return(f"Status: {status}\nOnline: {len(online)} people")

#function sends a message with kill button (callback server_kill). Message will dissapear in 5 seconds.
@restricted
async def request_server_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    term_msg = await context.bot.send_message(
        reply_markup=KbdConfirmMarkupInline,
        chat_id= context._user_id,
        text='Are you sure want to kill server? ' \
              'It may cause problem such as currupted save file and even ruin world completely.' \
              'This message will dissapear in 5 seconds.'
        )
    context.job_queue.run_once(callback=delete_message,when=5,chat_id=term_msg.chat_id,data=term_msg.message_id)

async def delete_message(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.delete_message(chat_id=job.chat_id, message_id=job.data)

#finds and kills valheim process
async def server_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    global status
    global serverprocess
    srv_process = get_server_process(server_proc_name)
    if(srv_process):
        # Forced stop of the valheim server
        print(f"Servers's PID is {srv_process.pid}. Killing")
        await context.bot.send_message(chat_id=context._user_id, text=f"Servers's PID is {srv_process.pid}. Terminating")
        srv_process.kill()
        status == 'Stopping'
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
        await request_server_run(update, context, mode = 'modded')
    if command == 'Run Vanilla':
        # await context.bot.send_message(chat_id = context._user_id, text=request_server_run(update, context))
        await request_server_run(update, context, mode = 'vanilla')
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
    global last_connected
    # print('in log parser func')
    fsize = os.path.getsize(log_path)
    async with aiofiles.open(log_path, mode='rb') as f:
        print(f'open file {log_path}')
        while True:
            await asyncio.sleep(0)
            line = await f.readline()
            if(not line):
                #print('wait')
                await asyncio.sleep(0.2)
                if fsize > os.path.getsize(log_path):
                    print('Reopening file')
                    break
                else:
                    fsize = os.path.getsize(log_path)
            else:
                line = str(line)
                # print(line)
                #TODO:commit and parse time skip
                if('skipspeed' in line):
                    print(f'Time has been fast forwarded. Day {line.partition("day:")[2].partition(" ")[0]} starts')
                    continue
                if ('<color=#FFEB04FF>I HAVE ARRIVED!</color>' in line) and len(last_connected):
                    online[last_connected[0]]= line.partition('<color=orange>')[2].partition('</color>')[0]
                    print(f'PLAYER {online[last_connected[0]]} JOINED SERVER')
                    last_connected.pop(0)
                    continue
                if 'Got handshake from client' in line:
                    steamid = line.split()[-1].strip("\\n'")
                    if steamid not in last_connected:
                        last_connected.append(steamid)
                        print(f'CONNECTION DETECTED {steamid}')
                    continue
                if 'Closing socket' in line:
                    steamid = line.split()[-1].strip("\\n'")
                    if steamid in online:
                        print(f'USER {online[steamid]} DISCONNECTED, STEAMID:{steamid}')
                        del(online[steamid])
                    continue             
                if 'Shuting down' in line:
                    status = 'Stopping'
                    print(f'SERVER STARTED SHUT DOWN AT {line.split(" ",2)[1]}')
                    continue
                if 'Net scene destroyed' in line:
                    status = 'Stopped'
                    online.clear()
                    print(f'SERVER SHUT DOWN COMPLETELY AT {line.split(" ",2)[1]}')
                    continue
                if 'Mono config path' in line:
                    status = 'Starting'
                    print(f'SERVER STARTING')
                    continue
                if 'Game server connected failed' in line:
                    status = 'Starting'
                    print(f'STARTING ERROR')
                    continue
                if 'Game server connected\\n' in line:
                    status = 'Online'
                    print(f'SERVER ONLINE')
                    continue

async def main():
    #Application setup
    # Create the Application and pass it your bot's token.
    persistence = PicklePersistence(filepath="status_cache")
    application = Application.builder().token(TOKEN).persistence(persistence).build()

    application.add_handler(MessageHandler(filters.Regex("^(Status|Run Modded|Run Vanilla|Stop|Online|Button)$"), process_control_panel))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, help))

    #callbackquery handlers
    #kill button handler
    handler = CallbackQueryHandler(server_kill, pattern="^kill$")
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
    handler = CommandHandler("runmodded", partial(request_server_run, mode='modded'))
    application.add_handler(handler)
    handler = CommandHandler("runvanilla", request_server_run)
    application.add_handler(handler)
    handler = CommandHandler("stop", request_server_stop)
    application.add_handler(handler)
    handler = CommandHandler("online", request_server_online)
    application.add_handler(handler)
    handler = CommandHandler("kill", request_server_kill)
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