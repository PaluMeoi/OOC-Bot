import logging
import os

from discord.ext import commands

logging.basicConfig(level=logging.INFO)

description = """FC Log Bot"""

bot = commands.Bot(command_prefix=commands.when_mentioned_or('fc!'), description=description)

extensions = [
    'cogs.fc'
    # , 'cogs.FCLogDBUpdater' TODO: Re-enable before releasing
]


@bot.event
async def on_ready():
    print('logged in as:')
    print('Username: ' + bot.user.name)
    print('---------')
    chan = int(os.environ['LOG_CHANNEL'])
    channel = bot.get_channel(chan)
    print(channel)
    await channel.send('Bot Ready: ' + bot.user.name)


if __name__ == '__main__':
    token = os.environ['DISCORD_TOKEN']

    for extension in extensions:
        bot.load_extension(extension)

    bot.run(token)
