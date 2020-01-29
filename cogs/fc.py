# cogs.fc.py

import os
import uuid
from datetime import datetime

import aiohttp
import discord
import pymongo
import xivapi
from discord.ext import commands


def setup(bot):
    bot.add_cog(FC(bot))


mongo = pymongo.MongoClient(os.environ['MONGO_URI'])
db = mongo[os.environ['MONGODB_NAME']]
xivapi_key = os.environ['XIVAPI_KEY']
fc_id = os.environ['FC_ID']


class FC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.discordcoll = db['DiscordMembers']

    async def _searchcharacter(self, world, forename, surname):
        async with aiohttp.ClientSession() as session:
            client = xivapi.Client(session=session, api_key=xivapi_key)
            results = await client.character_search(world=world, forename=forename, surname=surname)
            if results['Pagination']['Results'] != 1:
                return None
            else:
                character = results['Results'][0]
                return character

    async def _character_byid(self, id):
        async with aiohttp.ClientSession() as session:
            client = xivapi.Client(session=session, api_key=xivapi_key)
            results = await client.character_by_id(id)
            return results

    def _create_iam_embed(self,ctx: discord.Message, character, verified):
        name = character['Name']
        id = character['ID']
        avatar = character['Avatar']
        lodestone = '[{name}](https://na.finalfantasyxiv.com/lodestone/character/{id}/)'.format(name=name, id=id)
        discord_avatar = 'https://cdn.discordapp.com/avatars/{id}/{hash}.png'.format(id=ctx.author.id, hash=ctx.author.avatar)
        embed = discord.Embed(title=name, color=discord.Colour.green())
        embed.add_field(name='Lodestone', value=lodestone)
        embed.add_field(name='World', value=character['Server'])
        embed.set_thumbnail(url=avatar)
        embed.set_footer(text=ctx.author.nick, icon_url=discord_avatar)

        if verified:
            verified_field = '\u2705'
        else:
            verified_field = '\u274E'

        embed.add_field(name='Verified', value=verified_field)
        return embed

    def _get_char_by_discord(self, discordID):
        member = self.discordcoll.find_one({'DiscordID': discordID})
        character_ID = member['CharacterID']
        return character_ID

    @commands.command()
    async def iam(self, ctx: discord.Message, *args):
        char_embed = None
        verification_token = str(uuid.uuid4()).replace('-', '')
        # print(ctx.author.avatar)

        # If a world, forename and surname are provided
        if len(args) == 3:
            world, forename, surname = args
            _world = world.title()
            character = await self._searchcharacter(_world, forename, surname)

            if character is None:
                await ctx.send('Character not found. Alternatively retry the command using your character ID: `fc!iam '
                               '<character id>`', delete_after=10)
            else:
                character_id = int(character['ID'])

        elif len(args) == 1:
            invalid_message = 'Character not found or invalid character ID.'
            try:
                character_id = int(args[0])
                character = await self._character_byid(character_id)
                character = character['Character']
                print(character)
            except ValueError:
                await ctx.send(invalid_message, delete_after=10)
                return

        # Check if user already has a character
        current_character = self.discordcoll.find_one({'DiscordID': ctx.author.id})

        # If No character is currently set
        if current_character is None:
            record = {'DiscordID': ctx.author.id,
                      'CharacterID': character_id,
                      'Verified': False,
                      'Token': verification_token,
                      'Timestamp': datetime.utcnow()}
            self.discordcoll.insert_one(record)
            char_embed = self._create_iam_embed(ctx, character, False)

        elif current_character is not None:
            # Check if the character is the same
            if character_id == current_character['CharacterID']:
                self.discordcoll.update_one({'DiscordID': ctx.author.id}, {'$set': {'Timestamp': datetime.utcnow()}})
                char_embed = self._create_iam_embed(ctx, character, current_character['Verified'])

            # If the character is not the same
            else:
                record = {'CharacterID': character_id,
                          'Timestamp': datetime.utcnow(),
                          'Token': verification_token,
                          'Verified': False
                          }
                self.discordcoll.update_one({'DiscordID': ctx.author.id}, {'$set': record})
                char_embed = self._create_iam_embed(ctx, character, False)

        if char_embed is not False:
            await ctx.send(embed=char_embed, delete_after=20)

        # Delete command message after a period of time
        await ctx.message.delete()

    @commands.command()
    async def verify(self, ctx: discord.Message):
        # Check for saved character
        saved_character = self.discordcoll.find_one({'DiscordID': ctx.author.id})
        print(saved_character['Verified'])
        if saved_character is None:
            await ctx.send('No character saved, use `fc!iam` to save your character before trying again.',
                           delete_after=10)
        # Check if verification token in Bio
        else:
            token = saved_character['Token']
            lodestone_character = await self._character_byid(saved_character['CharacterID'])
            if saved_character['Verified']:
                embed = self._create_iam_embed(lodestone_character['Character'], True)
                await ctx.send('Character already verified.', embed=embed, delete_after=10)
            else:
                bio = lodestone_character['Character']['Bio']

                # Update if verification code in Bio
                if token in bio:
                    self.discordcoll.update_one({'DiscordID': ctx.author.id}, {'$set': {'Verified': True}})
                    embed = self._create_iam_embed(lodestone_character['Character'], True)
                    await ctx.send('Character successfully verified.', embed=embed, delete_after=10)
                # Send verification token to user if not found
                else:
                    msg = 'Add the following code to your bio on the lodestone and use `fc!verify` again to verify. \n' \
                          '```\n{token}\n```'.format(token=token)
                    await ctx.author.send(msg)

        try:
            await ctx.message.delete()
        finally:
            pass

    @commands.command()
    async def whois(self, ctx:discord.Message, *args):
        if len(args) == 0:
            user = ctx.author.id
        elif len(ctx.mentions) == 1:
            user = ctx.mentions[0].id
        elif len(args) == 3:
            pass # TODO: Add functionality for reverse search
        else:
            # TODO: Send help message and break




if __name__ == "__main__":
    pass
