import os
from datetime import datetime

import aiohttp
import discord
import pymongo
import xivapi
from discord.ext import tasks, commands


def setup(bot):
    bot.add_cog(FCLogDBUpdater(bot))


mongo = pymongo.MongoClient(os.environ['MONGO_URI'])
db = mongo[os.environ['MONGODB_NAME']]
xivapi_key = os.environ['XIVAPI_KEY']
fc_id = os.environ['FC_ID']


class FCLogDBUpdater(commands.Cog):
    def __init__(self, bot):
        self.statuscoll = db['StatusLog']
        self.namecoll = db['Names']
        self.membercoll = db['Members']
        self.configcoll = db['Config']
        self.bot = bot
        self.index = 0
        self.printer.start()

    async def send_update(self, title, color, character, details=None):

        StatusSetting = self.configcoll.find_one({'Setting': 'StatusUpdates'})
        channels = StatusSetting['Channels']
        webhooks = StatusSetting['Webhooks']
        # print(channels)

        logchan = int(os.environ['LOG_CHANNEL'])  # TODO: Allow for the reporting channel to be set independently

        name = character['Name']
        playerid = character['CharacterID']
        avatar = character['Avatar']

        lodestone_field = '[{name}](https://na.finalfantasyxiv.com/lodestone/character/{id}/)'.format(name=name,
                                                                                                      id=playerid)

        embed = discord.Embed(title=title, color=color)
        embed.set_thumbnail(url=avatar)
        embed.add_field(name='Lodestone', value=lodestone_field)

        if details is not None:
            for d in details:
                embed.add_field(name=d, value=details[d])

        # logchan = self.bot.get_channel(logchan)
        # await logchan.send(embed=embed)

        for c in channels:
            try:
                chan = int(c)
                channel = self.bot.get_channel(chan)
                await channel.send(embed=embed)
            finally:
                pass

        async with aiohttp.ClientSession() as session:
            WebhookConfig = StatusSetting['WebhookConfig']
            hook_avatar = WebhookConfig['Avatar']
            hook_name = WebhookConfig['Name']
            for hook in webhooks:
                try:
                    webhook = discord.Webhook.from_url(hook, adapter=discord.AsyncWebhookAdapter(session))
                    await webhook.send(embed=embed, avatar_url=hook_avatar, username=hook_name)
                finally:
                    pass

    async def fetch_members(self, fc_id, db):
        async with aiohttp.ClientSession() as session:
            client = xivapi.Client(session=session, api_key=xivapi_key)
            fc = await client.freecompany_by_id(fc_id, include_freecompany_members=True)
            raw_members = fc['FreeCompanyMembers']
            self.time = datetime.utcnow()
            members = list()
            new_members = list()
            memberids = list()
            firstrun = False

            if self.membercoll.count({}) == 0:
                print('First Run')
                firstrun = True

            # create a list of members
            for m in raw_members:
                member = {'CharacterID': m['ID'], 'Name': m['Name'], 'Rank': m['Rank'], 'Avatar': m['Avatar']}
                members.append(member)
                memberids.append(m['ID'])

            for m in members:
                # Add new members to the DB
                r = self.membercoll.find_one({'CharacterID': m['CharacterID']})
                if r is None:
                    # membercoll.insert_one(m)
                    self.namecoll.insert_one(
                        {'CharacterID': m['CharacterID'], 'Names': [m['Name']], 'Timestamp': self.time})
                    r = m

                    # Add to status log collection if not first run
                    if not firstrun:
                        await self._handle_newmember(m)

                new_members.append(m)

                # Check for Changes to Status
                if r['Name'] != m['Name']:
                    await self._handle_namechange(m, r)

                # Check for rank changes
                if r['Rank'] != m['Rank']:
                    # print('Rank')
                    await self._handle_rankchange(m, r)

            # Search for dismissed and left members
            # memberids = memberids[1:] # Testing Leave members
            old_member_ids = self.membercoll.distinct('CharacterID')
            for id in old_member_ids:
                if id not in memberids:
                    await self._handle_leave(id)

            self.membercoll.delete_many({})
            self.membercoll.insert_many(members)

        return members

    async def _handle_newmember(self, m):
        self.statuscoll.insert({'CharacterID': m['CharacterID'], 'Event': 'Joined', 'Timestamp': self.time})
        title = 'Joined: ' + m['Name']
        await self.send_update(title, discord.Colour.green(), m, details={'Rank': m['Rank']})

    async def _handle_namechange(self, new, old):
        self.namecoll.update_one({'CharacterID': new['CharacterID']}, {'$push': {'Names': new['Name']}})
        self.statuscoll.insert_one({'CharacterID': new['CharacterID'],
                                    'Event': 'Name Change',
                                    'Current': new['Name'],
                                    'Previous': old['Name'],
                                    'Timestamp': self.time})

        title = 'Name Change: ' + new['Name']
        await self.send_update(title, discord.Colour.orange(), new, details={'Old Name': old['Name']})

    async def _handle_rankchange(self, new, old):
        self.statuscoll.insert_one({'CharacterID': new['CharacterID'],
                                    'Event': 'Rank Change',
                                    'Current': new['Rank'],
                                    'Previous': old['Rank'],
                                    'Timestamp': self.time})

        title = 'Rank Change: ' + new['Name']
        det = {'Current Rank': new['Rank'], 'Previous Rank': old['Rank']}
        await self.send_update(title, discord.Colour.purple(), new, details=det)

    async def _handle_leave(self, id):
        old = self.membercoll.find_one({'CharacterID': id})
        # print(old)
        self.statuscoll.insert_one({'CharacterID': old['CharacterID'],
                                    'Event': 'Dismissed/Left',
                                    'Timestamp': self.time})
        title = 'Dismissed/Left: ' + old['Name']
        det = {'Rank': old['Rank']}
        await self.send_update(title, discord.Colour.red(), old, details=det)

    def cog_unload(self):
        self.printer.cancel()

    @tasks.loop(minutes=30)
    async def printer(self):
        await self.fetch_members(os.environ['FC_ID'], db)
        # print(members)


if __name__ == "__main__":
    pass
