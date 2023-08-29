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
import re
import threading
import aiofiles 
import os


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
valheimlog = 'valheimds.log'
print(f'TOKEN={TOKEN} and ADMINIDS={ADMINIDS}')
if(not (TOKEN and ADMINIDS)):
    print('Both TOKEN and ADMINIDS is necessary to run the bot. Supply them as environment variable and start the bot.')
    exit(1)

#start command handler and entry point for conversation handler
def find_server_process()->psutil.Process:
    processes = psutil.process_iter()
    for process in processes:
        if "./valheim_server.x86_64" in process.cmdline():
            return(process.pid)
    return 0

async def server_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pass

async def server_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if str(update.effective_user.id) in ADMINIDS:
        reply_text = 'Hello Admin'
    reply_text = 'hey'
    await update.message.reply_text(reply_text)  
    
#cancel command handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    current_jobs = context.job_queue.get_jobs_by_name(context._user_id)
    for job in current_jobs:
        job.schedule_removal()
    await update.message.reply_text('Cache clearead.\n/start to start again.')
    
#help command handler
async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text =  'To initiate bot send /start'
    await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())

#function sends control inline keyboard
async def send_control_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await context.bot.send_message(
            chat_id = context._user_id, text='Control panel', reply_markup=ControlPanelMarkup
        )
    return 0

async def server_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) not in ADMINIDS:
        await update.message.reply_text(f'Status user')
        
    await update.message.reply_text(f'Status admin')
    await update.message.reply_text(get_server_status())

def get_server_status():
    return(f"Server status:\nServer process PID {find_server_process()}")

async def server_online(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(get_server_online())

async def parse_server_output():
    global status
    global online
    async with aiofiles.open(valheimlog, mode='r') as f:
        async for line in f:
            if 'Got handshake from client' in line:
                steamid = line.split()[-1]
                if steamid not in online:
                    online.append(steamid)
            if 'Closing socket' in line:
                steamid = line.split()[-1]
                if steamid not in online:
                    online.remove(steamid)
            if 'Shuting down' in line:
                status = 'Shuting down'
            if 'Net scene destroyed' in line:
                status = 'Stopped'
                online.clear()
            if 'Got image' in line:
                status = 'Starting'
            if 'Game server connected' in line:
                status = 'Online'
            
async def get_server_online():
    return(f"Status: {status}\nOnline: {len(online)} people")

async def process_control_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await context.bot.send_message(chat_id = context._user_id, text=f'Processing command {query.data}')
    if query.data == 'Status':
        await context.bot.send_message(chat_id = context._user_id, text=get_server_status())
    
    #await query.message.edit_text(f'Pressed {query.data}')
    #await update.message.reply_text(f'Pressed {query.data}', reply_markup=ReplyKeyboardRemove())
    #reply_text(f'Pressed {query.data}', reply_markup=ReplyKeyboardRemove())
    #Separate thread for function which generates link
    #thread = threading.Thread(target=generate_url, args= (context,link,update.message.id,))
    #threads.append(thread)
    #thread.start()

    #context.job_queue.run_repeating(callback=server_status, interval=1, user_id=context._user_id)

def main() -> None:
    """Run the bot."""
    # Create the Application and pass it your bot's token.
    persistence = PicklePersistence(filepath="status_cache")
    application = Application.builder().token(TOKEN).persistence(persistence).build()
    
    # application.add_handler(
    #     MessageHandler(
    #         filters.Regex("^(Run|stop)$"), process_link
    #     )
    # )
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

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    

if __name__ == "__main__":
    main()