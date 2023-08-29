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
)
from telegram.constants import ParseMode
from typing import Final
import re
import threading 


# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
threads=[]

#start command handler and entry point for conversation handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_text = 'hey'
    await update.message.reply_text(reply_text)  
    

#show data command handler
async def show_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f'User_data: {facts_to_str(context.user_data)}'
    )
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

#converts data from user_data to readable view
def facts_to_str(user_data: Dict[str, str]) -> str:
    facts = [f"{key} - {value}" for key, value in user_data.items()]
    return "\n".join(facts).join(["\n", "\n"])

#function for the JOB which detects if link generated
async def check_status(context: ContextTypes.DEFAULT_TYPE) -> int:
    if not context.user_data:
        return 0
    
    msg_id, kbd = context.user_data.popitem()
    markup = InlineKeyboardMarkup(kbd)
    await context.bot.send_message(
            # chat_id = context._user_id, text='links plz', parse_mode=ParseMode.HTML, reply_to_message_id=msg_id, reply_markup=answer
            chat_id = context._user_id, text='links are valid for a few hours. Last row contains audio only', reply_to_message_id=msg_id, reply_markup=markup
        )
    
    context.job.schedule_removal()

    return 0

#text input handler
async def current_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Just send me a link.',reply_markup=ReplyKeyboardRemove())

#processing the link provided by user, if OK, show keyboard and call process_choice function
#SENDING LINK
async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('It looks like a link. Wait until I check it thoroughly, generate downloading links and send them to you.', reply_markup=ReplyKeyboardRemove())
    #Separate thread for function which generates link
    thread = threading.Thread(target=generate_url, args= (context,link,update.message.id,))
    threads.append(thread)
    thread.start()

    context.job_queue.run_repeating(callback=check_status, interval=1, user_id=context._user_id)

def main() -> None:
    """Run the bot."""
    # Create the Application and pass it your bot's token.
    persistence = PicklePersistence(filepath="status_cache")
    application = Application.builder().token(TOKEN).persistence(persistence).build()
    
    application.add_handler(
        MessageHandler(
            filters.Regex(yt_link_reg), process_link
        )
    )
    application.add_handler(
        MessageHandler(
        filters.TEXT & ~(filters.COMMAND | filters.Regex("^(Download|Cancel)$") | filters.Regex(yt_link_reg)), current_status
        )
    )

    start_handler = CommandHandler("start", start)
    application.add_handler(start_handler)
    cancel_handler = CommandHandler("cancel", cancel)
    application.add_handler(cancel_handler)
    help_handler = CommandHandler("help", help)
    application.add_handler(help_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()