# cogs.fc.py

import os
import uuid
import re
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

    def _create_iam_embed(self, ctx, character, verified, memberid=None):
        name = character['Name']
        id = character['ID']
        avatar = character['Avatar']
        lodestone = '[{name}](https://na.finalfantasyxiv.com/lodestone/character/{id}/)'.format(name=name, id=id)
        embed = discord.Embed(title=name, color=discord.Colour.green())
        embed.add_field(name='Lodestone', value=lodestone)
        embed.add_field(name='World', value=character['Server'])
        embed.set_thumbnail(url=avatar)
        if (ctx is not None) and (memberid is not None):
            member = ctx.guild.get_member(memberid)
            discord_avatar = 'https://cdn.discordapp.com/avatars/{id}/{hash}.png'.format(id=memberid,
                                                                                         hash=member.avatar)
            # footer = '{discord}#{discrim}'.format(discord=member.nick, discrim=ctx.author.discriminator)
            embed.set_footer(text=member.display_name, icon_url=discord_avatar)
        elif ctx is not None:
            discord_avatar = 'https://cdn.discordapp.com/avatars/{id}/{hash}.png'.format(id=ctx.author.id,
                                                                                         hash=ctx.author.avatar)
            # footer = '{discord}#{discrim}'.format(discord=ctx.author.nick, discrim=ctx.author.discriminator)
            embed.set_footer(text=ctx.author.disply_name, icon_url=discord_avatar) # TODO: Adjust so a user is passed instead of message context


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

    @commands.command(aliases=['whoami'])
    async def whois(self, ctx:discord.Message, *args):
        await ctx.trigger_typing()
        if len(args) == 0:
            user = ctx.author.id
            member = self.discordcoll.find_one({'DiscordID': user})
        elif len(args) == 1:
            m = re.search('(\d+)', args[0])
            user = int(m.group(0))
            member = self.discordcoll.find_one({'DiscordID': user})
        elif len(args) == 3:
            try:
                world, firstname, surname = args
                # Find the discord member with the given character
                character_result = await self._searchcharacter(world, firstname, surname)
                character_id = int(character_result['ID'])
                member = self.discordcoll.find_one({'CharacterID': character_id})
                if member is not None:
                    user = member['DiscordID']
            finally:
                pass
        else:
            # TODO: Send help message and break
            ctx.send("No character found associated with the user or bad arguments passed.")

        # Get Member's verified status
        if member is not None:
            verified = member['Verified']

            # Get the member's character id
            character_id = self._get_char_by_discord(user)
            character = await self._character_byid(character_id)
            embed = self._create_iam_embed(ctx, character['Character'], verified, member['DiscordID'])
            await ctx.send(embed=embed)
        else:
            character = await self._character_byid(character_id)
            embed = self._create_iam_embed(None, character['Character'], False, None)
            await ctx.send(embed=embed)
            # message = "No character associated with the user."
            # await ctx.send(message, delete_after=20)
            await ctx.message.delete()



if __name__ == "__main__":
    pass
