#!/usr/bin/env python3

import os
import random
import re
import string
import subprocess
import sys
import threading

import requests
import telebot

# SETTINGS
TEMP_FOLDER = "/tmp/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.181 Safari/537.36",
    "Accept-Encoding": "identity"
}

# MESSAGES
error_wrong_code = "❗️ Resource returned HTTP {} code. Maybe link is broken"
error_downloading = "⚠️ Unable to download file"
error_converting = "⚠️ Sorry, <code>youtube-dl</code> seems unable to convert this file"
message_start = """Hello! I am the Reddit mediaembed converter bot 📺

Just send me one of those Reddit mediaembed links."""
message_help = "Send me a link (https://reddit.com/mediaembed/...)"
message_starting = "🚀 Starting..."
message_converting = "☕️ Converting... {}"
message_uploading = "☁️ Uploading to Telegram..."
message_thanks = "🤩 Thank you!"


def update_status_message(message, text):
    try:
        bot.edit_message_text(chat_id=message.chat.id,
                              message_id=message.message_id,
                              text=text, parse_mode="HTML")
    except:
        pass


def rm(filename):
    """Delete file (like 'rm' command)"""
    try:
        os.remove(filename)
    except:
        pass


def random_string(length=12):
    """Random string of uppercase ASCII and digits"""
    return "".join(random.choice(string.ascii_uppercase + string.digits)
                   for _ in range(length))


def convert_worker(message, url):
    """Generic process spawned every time user sends a link"""
    global telegram_token
    filename = "".join([TEMP_FOLDER, random_string(), ".mp4"])

    # Tell user that we are working
    status_message = bot.reply_to(message, message_starting, parse_mode="HTML")

    # Try to fetch mpd URL
    if 'mediaembed' in url:
        try:
            r = requests.get(url, headers=HEADERS)
        except:
            update_status_message(status_message, error_downloading)
            return

        # Something went wrong on the server side
        if r.status_code != 200:
            update_status_message(status_message,
                                  error_wrong_code.format(r.status_code))
            return

        # Regex out the URL
        mpd_urls = re.findall('data-mpd-url="([^"]*)"', r.text)
        if len(mpd_urls) != 1:
            update_status_message(status_message, error_downloading)
            return

        mpd_url = mpd_urls[0]
    else:
        mpd_url = url

    print('Downloading {} -> {}'.format(url, mpd_url))

    # Start youtube-dl
    update_status_message(status_message, message_converting.format('0%'))
    try:
        youtubedl_process = subprocess.Popen(["youtube-dl",
                                              "--newline",
                                              "--output", filename,
                                              mpd_url
                                              ],
                                             stdout=subprocess.PIPE)
    except:
        update_status_message(status_message, error_converting)
        # Clean up and close pipe explicitly
        rm(filename)
        return

    # Track progress
    while True:
        line = youtubedl_process.stdout.readline()
        if not line:
            break
        match = re.match(r'^\[download\]  ([^%]*%)', line.decode('utf-8'))
        if match:
            update_status_message(status_message,
                                  message_converting.format(match.groups()[0]))

    # Update return code
    youtubedl_process.poll()

    # Exit in case of error with youtube-dl
    if youtubedl_process.returncode != 0:
        update_status_message(status_message, error_converting)
        # Clean up and close pipe explicitly
        rm(filename)
        return

    # Get duration of the video
    video_duration = subprocess.run(["ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        filename
    ], stdout=subprocess.PIPE).stdout.decode("utf-8").strip()
    video_duration = round(float(video_duration))

    # Get width and height
    video_props = subprocess.run(["ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries","stream=width,height",
        "-of", "csv=s=x:p=0",
        filename
    ], stdout=subprocess.PIPE).stdout.decode("utf-8").strip()
    video_width, video_height = video_props.split('\n', 1)[0].split('x')

    # Upload to Telegram
    update_status_message(status_message, message_uploading)
    mp4 = open(filename, "rb")
    requests.post(
        f"https://api.telegram.org/bot{telegram_token}/sendVideo",
        data={
            "chat_id": message.chat.id,
            "duration": video_duration,
            "width": video_width,
            "height": video_height,
            "reply_to_message_id": message.message_id,
            "supports_streaming": True
        },
        files=[
            ("video", (random_string()+".mp4", mp4, "video/mp4")),
        ]
    )
    bot.delete_message(message.chat.id, status_message.message_id)

    # Clean up
    mp4.close()
    rm(filename)

    print('Done with {}'.format(url))


tokenfile = "token.txt"
if len(sys.argv) == 2:
    tokenfile = sys.argv[1]

try:
    with open(tokenfile, "r") as f:
        telegram_token = f.read().strip()
except FileNotFoundError:
    print("Put your Telegram bot token to 'token.txt' file")
    exit(1)
bot = telebot.TeleBot(telegram_token)


@bot.message_handler(commands=["start", "help"])
def start_help(message):
    bot.send_message(message.chat.id, message_start, parse_mode="HTML")
    bot.send_message(message.chat.id, message_help, parse_mode="HTML")


# Handle mediaembed
ME_REGEXP = r"(https:\/\/(www\.)?reddit.com/mediaembed.*)"
@bot.message_handler(regexp=ME_REGEXP)
def handle_urls(message):
    # Grab first found link
    url = re.findall(ME_REGEXP, message.text)[0]
    threading.Thread(
        target=convert_worker,
        kwargs={
            "message": message,
            "url": url[0]
        }
    ).start()

# Handle v.redd.it
V_REGEXP = r"(https:\/\/v.redd.it/.*)"
@bot.message_handler(regexp=V_REGEXP)
def handle_urls(message):
    # Grab first found link
    url = re.findall(V_REGEXP, message.text)[0]
    threading.Thread(
        target=convert_worker,
        kwargs={
            "message": message,
            "url": url
        }
    ).start()


# Handle good bot
GOODBOT_REGEXP = r"(?i)good bot"
@bot.message_handler(regexp=GOODBOT_REGEXP)
def handle_urls(message):
    # Grab first found link
    status_message = bot.reply_to(message, message_thanks, parse_mode="HTML")


bot.polling(none_stop=True)
