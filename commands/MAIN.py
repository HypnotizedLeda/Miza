print = PRINT


# Default and standard command categories to enable.
basic_commands = frozenset(("main", "string", "admin"))
standard_commands = default_commands = basic_commands.union(("voice", "image", "fun"))

help_colours = fcdict({
    None: 0xfffffe,
    "main": 0xff0000,
    "string": 0x00ff00,
    "admin": 0x0000ff,
    "voice": 0xff00ff,
    "image": 0xffff00,
    "fun": 0x00ffff,
    "owner": 0xbf7fff,
    "nsfw": 0xff9f9f,
    "misc": 0x007f00,
})
help_emojis = fcdict((
    (None, "♾"),
    ("main", "🌐"),
    ("string", "🔢"),
    ("admin", "🕵️‍♀️"),
    ("voice", "🎼"),
    ("image", "🖼"),
    ("fun", "🙃"),
    ("owner", "💜"),
    ("nsfw", "🔞"),
    ("misc", "🌌"),
))
help_descriptions = fcdict((
    (None, "N/A"),
    ("main", "General commands, mostly involves individual users"),
    ("string", "Text-based commands, usually helper tools"),
    ("admin", "Moderation-based, used to help staffing servers"),
    ("voice", "Play, convert, or download songs through VC"),
    ("image", "Create or edit images, animations, and videos"),
    ("fun", "Text-based games and webhook management"),
    ("owner", "Restricted owner-only commands; highly volatile"),
    ("nsfw", "Not Safe For Work; only usable in 18+ channels"),
    ("misc", "Miscellaneous; restricted to trusted servers"),
))


class Help(Command):
    name = ["❓", "❔", "?", "Halp"]
    description = "Shows a list of usable commands, or gives a detailed description of a command."
    usage = "<(command|category)>?"
    flags = "v"
    no_parse = True
    slash = True

    async def __call__(self, bot, argv, user, message, original=None, **void):
        bot = self.bot
        guild = message.guild
        channel = message.channel
        prefix = "/" if getattr(message, "slash", None) else bot.get_prefix(guild.id)
        if " " in prefix:
            prefix += " "
        embed = discord.Embed()
        embed.set_author(name="❓ Help ❓", icon_url=best_url(user), url=bot.webserver)
        argv = full_prune(argv).replace("*", "").replace("_", "").replace("||", "")
        comm = None
        if argv in bot.categories:
            catg = argv
        elif argv in bot.commands:
            comm = argv
            catg = bot.commands[argv][0].catg.casefold()
        else:
            catg = None
        if catg not in bot.categories:
            catg = None
        content = None
        enabled = bot.get_enabled(channel)
        category_repr = lambda catg: catg.capitalize() + (" [DISABLED]" if catg.lower() not in enabled else "")
        if comm:
            com = bot.commands[comm][0]
            a = ", ".join(n.strip("_") for n in com.name) or "[none]"
            content = (
                f"[Category] {category_repr(com.catg)}\n"
                + f"[Usage] {prefix}{com.parse_name()} {com.usage}\n"
                + f"[Aliases] {a}\n"
                + f"[Effect] {com.parse_description()}\n"
                + f"[Level] {com.min_display}"
            )
            x = com.rate_limit
            if x:
                if isinstance(x, collections.abc.Sequence):
                    x = x[not bot.is_trusted(getattr(guild, "id", 0))]
                content += f"\n[Rate Limit] {sec2time(x)}"
            content = ini_md(content)
        else:
            if getattr(message, "slash", None):
                content = (
                    f"```callback-main-help-{user.id}-\n{user.display_name} has asked for help!```"
                    + f"Yo! Use the menu below to select from my command list!\n"
                    + f"Alternatively, visit <{bot.webserver}/mizatlas> for a full command list and tester.\n"
                    + f"Unsure about anything, or have a bug to report? check out the support server: <{bot.rcc_invite}>!\n"
                    + f"Finally, if you're an admin and wish to disable me in a particular channel, check out `{prefix}ec`!"
                )
            else:
                embed.description = (
                    f"```callback-main-help-{user.id}-\n{user.display_name} has asked for help!```"
                    + f"Yo! Use the menu below to select from my command list!\n"
                    + f"Alternatively, visit [`mizatlas`]({bot.webserver}/mizatlas) for a full command list and tester.\n"
                    + f"Unsure about anything, or have a bug to report? check out the [`support server`]({bot.rcc_invite})!\n"
                    + f"Finally, if you're an admin and wish to disable me in a particular channel, check out `{prefix}ec`!"
                )
        embed.colour = discord.Colour(help_colours[catg])
        if not catg:
            coms = chain.from_iterable(v for k, v in bot.categories.items() if k in standard_commands)
        else:
            coms = bot.categories[catg]
        coms = sorted(coms, key=lambda c: c.parse_name())
        catsel = [cdict(
            emoji=cdict(id=None, name=help_emojis[c]),
            label=category_repr(c),
            value=c,
            description=help_descriptions[c],
            default=catg == c,
        ) for c in standard_commands if c in bot.categories]
        comsel = [cdict(
            emoji=cdict(id=None, name=c.emoji) if getattr(c, "emoji", None) else None,
            label=lim_str(prefix + " " * (" " in prefix) + c.parse_name() + " " + c.usage, 25, mode=None),
            value=c.parse_name().casefold(),
            description=lim_str(c.parse_description(), 50, mode=None),
            default=comm and com == c,
        ) for i, c in enumerate(coms) if i < 25]
        catmenu = cdict(
            type=3,
            custom_id="\x7f0",
            options=catsel,
            min_values=0,
            placeholder=category_repr(catg) if catg else "Choose a category...",
        )
        commenu = cdict(
            type=3,
            custom_id="\x7f1",
            options=comsel,
            min_values=0,
            placeholder=com.parse_name() if comm else "Choose a command...",
        )
        buttons = [[catmenu], [commenu]]
        if original:
            if not getattr(message, "slash", None) and content:
                create_task(bot.ignore_interaction(original))
                embed.description = f"```callback-main-help-{user.id}-\n{user.display_name} has asked for help!```" + content
                try:
                    sem = EDIT_SEM[message.channel.id]
                except KeyError:
                    sem = EDIT_SEM[message.channel.id] = Semaphore(5.1, 256, rate_limit=5)
                async with sem:
                    await Request(
                        f"https://discord.com/api/v9/channels/{message.channel.id}/messages/{message.id}",
                        data=json.dumps(dict(
                            embed=embed.to_dict(),
                            components=restructure_buttons(buttons),
                        )),
                        method="PATCH",
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bot {bot.token}",
                        },
                        bypass=False,
                        aio=True,
                    )
            elif content:
                create_task(interaction_response(bot, original, content))
                if not getattr(message, "slash", None):
                    try:
                        sem = EDIT_SEM[message.channel.id]
                    except KeyError:
                        sem = EDIT_SEM[message.channel.id] = Semaphore(5.1, 256, rate_limit=5)
                    async with sem:
                        await Request(
                            f"https://discord.com/api/v9/channels/{message.channel.id}/messages/{message.id}",
                            data=json.dumps(dict(
                                components=restructure_buttons(buttons),
                            )),
                            method="PATCH",
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": f"Bot {bot.token}",
                            },
                            bypass=False,
                            aio=True,
                        )
            else:
                await interaction_patch(bot, original, buttons=buttons)
            return
        elif getattr(message, "slash", None):
            await interaction_response(bot, message, content, buttons=buttons)
        else:
            if not embed.description:
                embed.description = f"```callback-main-help-{user.id}-\n{user.display_name} has asked for help!```" + content
            await send_with_reply(channel, message, embed=embed, buttons=buttons)
        return

    async def _callback_(self, message, reaction, user, vals, perm, **void):
        u_id = int(vals)
        if reaction is None or u_id != user.id and perm < 3:
            return
        await self.__call__(self.bot, as_str(reaction), user, message=message, original=message)


class Hello(Command):
    name = ["👋", "Hi", "Hi!", "Hewwo", "Herro", "'sup", "Hey", "Greetings", "Welcome", "Bye", "Cya", "Goodbye"]
    description = "Sends a greeting message. Useful for checking whether the bot is online."
    usage = "<user>?"
    slash = True

    async def __call__(self, bot, user, name, argv, guild, **void):
        if "dailies" in bot.data:
            bot.data.dailies.progress_quests(user, "talk")
        if argv:
            user = await bot.fetch_user_member(argv, guild)
        elif bot.is_owner(user):
            return "👋"
        if name in ("bye", "cya", "goodbye"):
            start = choice("Bye", "Cya", "Goodbye")
        else:
            start = choice("Hi", "Hello", "Hey", "'sup")
        middle = choice(user.name, user.display_name)
        if name in ("bye", "cya", "goodbye"):
            end = choice("", "See you soon!", "Have a good one!", "Later!", "Talk to you again sometime!", "Was nice talking to you!")
        else:
            end = choice("", "How are you?", "Can I help you?", "What can I do for you today?", "Nice to see you!", "Great to see you!", "Always good to see you!")
        out = "👋 " + start + ", `" + middle + "`!"
        if end:
            out += " " + end
        return out


class Perms(Command):
    server_only = True
    name = ["DefaultPerms", "ChangePerms", "Perm", "ChangePerm", "Permissions"]
    description = "Shows or changes a user's permission level."
    usage = "<0:users>* <1:new_level>? <default{?d}>? <hide{?h}>?"
    flags = "fhd"
    multi = True
    slash = True

    async def __call__(self, bot, args, argl, user, name, perm, channel, guild, flags, **void):
        if name == "defaultperms":
            users = (guild.get_role(guild.id),)
        else:
            # Get target user from first argument
            users = await bot.find_users(argl, args, user, guild, roles=True)
        if not users:
            raise LookupError("No results found.")
        for t_user in users:
            t_perm = round_min(bot.get_perms(t_user.id, guild))
            # If permission level is given, attempt to change permission level, otherwise get current permission level
            if args or "d" in flags:
                name = str(t_user)
                if "d" in flags:
                    o_perm = round_min(bot.get_perms(t_user.id, guild))
                    bot.remove_perms(t_user.id, guild)
                    c_perm = round_min(bot.get_perms(t_user.id, guild))
                    m_perm = max(abs(t_perm), abs(c_perm), 2) + 1
                    if not perm < m_perm and not isnan(m_perm):
                        create_task(channel.send(css_md(f"Changed permissions for {sqr_md(name)} in {sqr_md(guild)} from {sqr_md(t_perm)} to the default value of {sqr_md(c_perm)}.")))
                        continue
                    reason = f"to change permissions for {name} in {guild} from {t_perm} to {c_perm}"
                    bot.set_perms(t_user.id, guild, o_perm)
                    raise self.perm_error(perm, m_perm, reason)
                orig = t_perm
                expr = " ".join(args)
                num = await bot.eval_math(expr, orig)
                c_perm = round_min(num)
                if t_perm is nan or isnan(c_perm):
                    m_perm = nan
                else:
                    # Required permission to change is absolute level + 1, with a minimum of 3
                    m_perm = max(abs(t_perm), abs(c_perm), 2) + 1
                if not perm < m_perm and not isnan(m_perm):
                    if not m_perm < inf and guild.owner_id != user.id and not isnan(perm):
                        raise PermissionError("Must be server owner to assign non-finite permission level.")
                    bot.set_perms(t_user.id, guild, c_perm)
                    if "h" in flags:
                        return
                    create_task(channel.send(css_md(f"Changed permissions for {sqr_md(name)} in {sqr_md(guild)} from {sqr_md(t_perm)} to {sqr_md(c_perm)}.")))
                    continue
                reason = f"to change permissions for {name} in {guild} from {t_perm} to {c_perm}"
                raise self.perm_error(perm, m_perm, reason)
            create_task(channel.send(css_md(f"Current permissions for {sqr_md(t_user)} in {sqr_md(guild)}: {sqr_md(t_perm)}.")))


class EnabledCommands(Command):
    server_only = True
    name = ["EC", "Enable"]
    min_display = "0~3"
    description = "Shows, enables, or disables a command category in the current channel."
    usage = "(enable|disable|clear)? <category>? <server-wide(?s)> <list{?l}>? <hide{?h}>?"
    flags = "aedlhrs"
    slash = True

    def __call__(self, argv, args, flags, user, channel, guild, perm, name, **void):
        bot = self.bot
        update = bot.data.enabled.update
        enabled = bot.data.enabled
        if "s" in flags:
            target = guild
            mention = lambda *args: str(guild)
        else:
            target = channel
            mention = channel_mention
        # Flags to change enabled commands list
        if any(k in flags for k in "acder"):
            req = 3
            if perm < req:
                reason = f"to change enabled command list for {channel_repr(target)}"
                raise self.perm_error(perm, req, reason)
        else:
            req = 0
        if not args or argv.casefold() == "all" or "r" in flags:
            if "l" in flags:
                return css_md(f"Standard command categories:\n[{', '.join(standard_commands)}]")
            if "e" in flags or "a" in flags:
                categories = set(standard_commands)
                if target.id in enabled:
                    enabled[target.id] = categories.union(enabled[target.id])
                else:
                    enabled[target.id] = categories
                if "h" in flags:
                    return
                return css_md(f"Enabled all standard command categories in {sqr_md(target)}.")
            if "r" in flags:
                enabled.pop(target.id, None)
                if "h" in flags:
                    return
                return css_md(f"Reset enabled status of all commands in {sqr_md(target)}.")
            if "d" in flags:
                enabled[target.id] = set()
                if "h" in flags:
                    return
                return css_md(f"Disabled all commands in {sqr_md(target)}.")
            temp = bot.get_enabled(target)
            if not temp:
                return ini_md(f"No currently enabled commands in {sqr_md(target)}.")
            return f"Currently enabled command categories in {mention(target.id)}:\n{ini_md(iter2str(temp))}"
        if not req:
            catg = argv.casefold()
            if not bot.is_trusted(guild) and catg not in standard_commands:
                raise PermissionError(f"Elevated server priviliges required for specified command category.")
            if catg not in bot.categories:
                raise LookupError(f"Unknown command category {argv}.")
            if catg in bot.get_enabled(target):
                return css_md(f"Command category {sqr_md(catg)} is currently enabled in {sqr_md(target)}.")
            return css_md(f'Command category {sqr_md(catg)} is currently disabled in {sqr_md(target)}. Use "{bot.get_prefix(guild)}{name} enable" to enable.')
        args = [i.casefold() for i in args]
        for catg in args:
            if not bot.is_trusted(guild) and catg not in standard_commands:
                raise PermissionError(f"Elevated server priviliges required for specified command category.")
            if not catg in bot.categories:
                raise LookupError(f"Unknown command category {catg}.")
        curr = bot.get_enabled(target)
        if target.id not in enabled:
            enabled[target.id] = curr if type(curr) is set else set(curr)
        for catg in args:
            if "d" not in flags:
                if catg not in curr:
                    if type(curr) is set:
                        curr.add(catg)
                    else:
                        curr.append(catg)
                    update(target.id)
            else:
                if catg in curr:
                    curr.remove(catg)
                    update(target.id)
        check = curr if type(curr) is set else frozenset(curr)
        if check == default_commands:
            enabled.pop(target.id)
        if "h" in flags:
            return
        category = "category" if len(args) == 1 else "categories"
        action = "Enabled" if "d" not in flags else "Disabled"
        return css_md(f"{action} command {category} {sqr_md(', '.join(args))} in {sqr_md(target)}.")


class Prefix(Command):
    name = ["ChangePrefix"]
    min_display = "0~3"
    description = "Shows or changes the prefix for ⟨MIZA⟩'s commands for this server."
    usage = "<new_prefix>? <default{?d}>?"
    flags = "hd"
    umap = {c: "" for c in ZeroEnc}
    umap["\u200a"] = ""
    utrans = "".maketrans(umap)
    slash = True

    def __call__(self, argv, guild, perm, bot, flags, **void):
        pref = bot.data.prefixes
        update = self.data.prefixes.update
        if "d" in flags:
            if guild.id in pref:
                pref.pop(guild.id)
            return css_md(f"Successfully reset command prefix for {sqr_md(guild)}.")
        if not argv:
            return css_md(f"Current command prefix for {sqr_md(guild)}: {sqr_md(bot.get_prefix(guild))}.")
        req = 3
        if perm < req:
            reason = f"to change command prefix for {guild}"
            raise self.perm_error(perm, req, reason)
        prefix = argv
        if not prefix.isalnum():
            prefix = prefix.translate(self.utrans)
        # Backslash is not allowed, it is used to escape commands normally
        if prefix.startswith("\\"):
            raise TypeError("Prefix must not begin with backslash.")
        pref[guild.id] = prefix
        if "h" not in flags:
            return css_md(f"Successfully changed command prefix for {sqr_md(guild)} to {sqr_md(argv)}.")


class Loop(Command):
    time_consuming = 3
    _timeout_ = 12
    name = ["For", "Rep", "While"]
    min_level = 1
    min_display = "1+"
    description = "Loops a command."
    usage = "<0:iterations> <1:command>+"
    rate_limit = (3, 7)

    async def __call__(self, args, argv, message, channel, bot, perm, user, guild, **void):
        if not args:
            # Ah yes, I made this error specifically for people trying to use this command to loop songs 🙃
            raise ArgumentError("Please input loop iterations and target command. For looping songs in voice, consider using the aliases LoopQueue and Repeat under the AudioSettings command.")
        num = await bot.eval_math(args[0])
        iters = round(num)
        # Bot owner bypasses restrictions
        if not isnan(perm):
            if iters > 32 and not bot.is_trusted(guild.id):
                raise PermissionError(f"Elevated server priviliges required to execute loop of greater than 32 iterations.")
            elif iters > 256:
                raise PermissionError("Must be owner to execute loop of more than 256 iterations.")
        func = func2 = " ".join(args[1:])
        func = func.lstrip()
        if not isnan(perm):
            # Detects when an attempt is made to loop the loop command
            for n in self.name:
                if (
                    (bot.get_prefix(guild) + n).upper() in func.replace(" ", "").upper()
                ) or (
                    (str(bot.id) + ">" + n).upper() in func.replace(" ", "").upper()
                ):
                    raise PermissionError("Must be owner to execute nested loop.")
        func2 = func2.split(None, 1)[-1]
        create_task(send_with_react(
            channel,
            italics(css_md(f"Looping {sqr_md(func)} {iters} time{'s' if iters != 1 else ''}...")),
            reacts=["❎"],
            reference=message,
        ))
        fake_message = copy.copy(message)
        fake_message.content = func2
        for i in range(iters):
            curr_message = await bot.fetch_message(message.id, channel)
            if getattr(message, "deleted", None) or getattr(curr_message, "deleted", None):
                break
            loop = i < iters - 1
            t = utc()
            # Calls process_message with the argument containing the looped command.
            delay = await bot.process_message(fake_message, func, loop=loop)
            # Must abide by command rate limit rules
            delay = delay + t - utc()
            if delay > 0:
                await asyncio.sleep(delay)


class Avatar(Command):
    name = ["PFP", "Icon"]
    description = "Sends a link to the avatar of a user or server."
    usage = "<objects>*"
    multi = True
    slash = True

    async def getGuildData(self, g):
        # Gets icon display of a server and returns as an embed.
        url = to_png(g.icon_url)
        name = g.name
        colour = await self.bot.data.colours.get(to_png_ex(g.icon_url))
        emb = discord.Embed(colour=colour)
        emb.set_thumbnail(url=url)
        emb.set_image(url=url)
        emb.set_author(name=name, icon_url=url, url=url)
        emb.description = f"{sqr_md(name)}({url})"
        return emb

    async def getMimicData(self, p):
        # Gets icon display of a mimic and returns as an embed.
        url = to_png(p.url)
        name = p.name
        colour = await self.bot.data.colours.get(to_png_ex(p.url))
        emb = discord.Embed(colour=colour)
        emb.set_thumbnail(url=url)
        emb.set_image(url=url)
        emb.set_author(name=name, icon_url=url, url=url)
        emb.description = f"{sqr_md(name)}({url})"
        return emb

    async def __call__(self, argv, argl, channel, guild, bot, user, **void):
        iterator = argl if argl else (argv,)
        embs = set()
        for argv in iterator:
            with self.bot.ExceptionSender(channel):
                with suppress(StopIteration):
                    if argv:
                        if is_url(argv) or argv.startswith("discord.gg/"):
                            g = await bot.fetch_guild(argv)
                            emb = await self.getGuildData(g)
                            embs.add(emb)
                            raise StopIteration
                        u_id = argv
                        with suppress():
                            u_id = verify_id(u_id)
                        u = guild.get_member(u_id)
                        g = None
                        while u is None and g is None:
                            with suppress():
                                u = bot.get_member(u_id, guild)
                                break
                            with suppress():
                                try:
                                    u = bot.get_user(u_id)
                                except:
                                    if not bot.in_cache(u_id):
                                        u = await bot.fetch_user(u_id)
                                    else:
                                        raise
                                break
                            if type(u_id) is str and "@" in u_id and ("everyone" in u_id or "here" in u_id):
                                g = guild
                                break
                            try:
                                p = bot.get_mimic(u_id, user)
                                emb = await self.getMimicData(p)
                                embs.add(emb)
                            except:
                                pass
                            else:
                                raise StopIteration
                            with suppress():
                                g = bot.cache.guilds[u_id]
                                break
                            with suppress():
                                g = bot.cache.roles[u_id].guild
                                break
                            with suppress():
                                g = bot.cache.channels[u_id].guild
                            with suppress():
                                u = await bot.fetch_member_ex(u_id, guild)
                                break
                            raise LookupError(f"No results for {argv}.")     
                        if g:
                            emb = await self.getGuildData(g)    
                            embs.add(emb)   
                            raise StopIteration         
                    else:
                        u = user
                    name = str(u)
                    url = await self.bot.get_proxy_url(u)
                    colour = await self.bot.get_colour(u)
                    emb = discord.Embed(colour=colour)
                    emb.set_thumbnail(url=url)
                    emb.set_image(url=url)
                    emb.set_author(name=name, icon_url=url, url=url)
                    emb.description = f"{sqr_md(name)}({url})"
                    embs.add(emb)
        bot.send_embeds(channel, embeds=embs)


class Info(Command):
    name = ["🔍", "🔎", "UserInfo", "ServerInfo", "WhoIs"]
    description = "Shows information about the target user or server."
    usage = "<objects>* <verbose{?v}>?"
    flags = "v"
    rate_limit = 1
    multi = True
    slash = True
    usercmd = True

    async def getGuildData(self, g, flags={}):
        bot = self.bot
        url = await bot.get_proxy_url(g)
        name = g.name
        try:
            u = g.owner
        except (AttributeError, KeyError):
            u = None
        colour = await self.bot.data.colours.get(to_png_ex(g.icon_url))
        emb = discord.Embed(colour=colour)
        emb.set_thumbnail(url=url)
        emb.set_author(name=name, icon_url=url, url=url)
        if u is not None:
            d = user_mention(u.id)
        else:
            d = ""
        if g.description:
            d += code_md(g.description)
        emb.description = d
        emb.add_field(name="Server ID", value=str(g.id), inline=0)
        emb.add_field(name="Creation time", value=str(g.created_at) + "\n" + dyn_time_diff(utc_dt().timestamp(), g.created_at.timestamp()) + " ago", inline=1)
        if "v" in flags:
            with suppress(AttributeError, KeyError):
                emb.add_field(name="Region", value=str(g.region), inline=1)
                emb.add_field(name="Nitro boosts", value=str(g.premium_subscription_count), inline=1)
        with suppress(AttributeError):
            emb.add_field(name="Text channels", value=str(len(g.text_channels)), inline=1)
            emb.add_field(name="Voice channels", value=str(len(g.voice_channels)), inline=1)
        emb.add_field(name="Member count", value=str(g.member_count), inline=1)
        return emb

    async def getMimicData(self, p, flags={}):
        url = to_png(p.url)
        name = p.name
        colour = await self.bot.data.colours.get(to_png_ex(p.url))
        emb = discord.Embed(colour=url)
        emb.set_thumbnail(url=url)
        emb.set_author(name=name, icon_url=url, url=url)
        d = f"{user_mention(p.u_id)}{fix_md(p.id)}"
        if p.description:
            d += code_md(p.description)
        emb.description = d
        emb.add_field(name="Mimic ID", value=str(p.id), inline=0)
        emb.add_field(name="Name", value=str(p.name), inline=0)
        emb.add_field(name="Prefix", value=str(p.prefix), inline=1)
        emb.add_field(name="Creation time", value=str(datetime.datetime.fromtimestamp(p.created_at)) + "\n" + dyn_time_diff(utc_dt().timestamp(), p.created_at) + " ago", inline=1)
        if "v" in flags:
            emb.add_field(name="Gender", value=str(p.gender), inline=1)
            ctime = datetime.datetime.fromtimestamp(p.birthday)
            age = (utc_dt() - ctime).total_seconds() / TIMEUNITS["year"]
            emb.add_field(name="Birthday", value=str(ctime), inline=1)
            emb.add_field(name="Age", value=str(round_min(round(age, 1))), inline=1)
        return emb

    async def __call__(self, argv, argl, name, guild, channel, bot, user, flags, **void):
        iterator = argl if argl else (argv,)
        embs = set()
        for argv in iterator:
            if argv.startswith("<") and argv[-1] == ">":
                argv = argv[1:-1]
            with self.bot.ExceptionSender(channel):
                with suppress(StopIteration):
                    if argv:
                        if is_url(argv) or argv.startswith("discord.gg/"):
                            g = await bot.fetch_guild(argv)
                            emb = await self.getGuildData(g, flags)
                            embs.add(emb)
                            raise StopIteration
                        u_id = argv
                        with suppress():
                            u_id = verify_id(u_id)
                        u = guild.get_member(u_id) if type(u_id) is int else None
                        g = None
                        while u is None and g is None:
                            with suppress():
                                u = bot.get_member(u_id, guild)
                                break
                            with suppress():
                                try:
                                    u = bot.get_user(u_id)
                                except:
                                    if not bot.in_cache(u_id):
                                        u = await bot.fetch_user(u_id)
                                    else:
                                        raise
                                break
                            if type(u_id) is str and "@" in u_id and ("everyone" in u_id or "here" in u_id):
                                g = guild
                                break
                            if "server" in name:
                                with suppress():
                                    g = await bot.fetch_guild(u_id)
                                    break
                                with suppress():
                                    role = await bot.fetch_role(u_id, g)
                                    g = role.guild
                                    break
                                with suppress():
                                    channel = await bot.fetch_channel(u_id)
                                    g = channel.guild
                                    break
                            try:
                                p = bot.get_mimic(u_id, user)
                                emb = await self.getMimicData(p, flags)
                                embs.add(emb)
                            except:
                                pass
                            else:
                                raise StopIteration
                            with suppress():
                                g = bot.cache.guilds[u_id]
                                break
                            with suppress():
                                g = bot.cache.roles[u_id].guild
                                break
                            with suppress():
                                g = bot.cache.channels[u_id].guild
                            with suppress():
                                u = await bot.fetch_member_ex(u_id, guild)
                                break
                            raise LookupError(f"No results for {argv}.")
                        if g:
                            emb = await self.getGuildData(g, flags)
                            embs.add(emb)
                            raise StopIteration
                    elif "server" not in name:
                        u = user
                    else:
                        if not hasattr(guild, "ghost"):
                            emb = await self.getGuildData(guild, flags)
                            embs.add(emb)
                            raise StopIteration
                        else:
                            u = bot.user
                    u = await bot.fetch_user_member(u.id, guild)
                    member = guild.get_member(u.id)
                    name = str(u)
                    url = await bot.get_proxy_url(u)
                    st = deque()
                    if u.id == bot.id:
                        st.append("Myself 🙃")
                        is_self = True
                    else:
                        is_self = False
                    if bot.is_owner(u.id):
                        st.append("My owner ❤️")
                    is_sys = False
                    if getattr(u, "system", None):
                        st.append("Discord System ⚙️")
                        is_sys = True
                    uf = getattr(u, "public_flags", None)
                    is_bot = False
                    if uf:
                        if uf.system and not is_sys:
                            st.append("Discord System ⚙️")
                        if uf.staff:
                            st.append("Discord Staff ⚠️")
                        if uf.partner:
                            st.append("Discord Partner 🎀:")
                        if uf.bug_hunter_level_2:
                            st.append("Bug Hunter Lv.2 🕷️")
                        elif uf.bug_hunter:
                            st.append("Bug Hunter 🐛")
                        is_hype = False
                        if uf.hypesquad_bravery:
                            st.append("HypeSquad Bravery 🛡️")
                            is_hype = True
                        if uf.hypesquad_brilliance:
                            st.append("HypeSquad Brilliance 🌟")
                            is_hype = True
                        if uf.hypesquad_balance:
                            st.append("HypeSquad Balance 💠")
                            is_hype = True
                        if uf.hypesquad and not is_hype:
                            st.append("HypeSquad 👀")
                        if uf.early_supporter:
                            st.append("Discord Early Supporter 🌄")
                        if uf.team_user:
                            st.append("Discord Team User 🧑‍🤝‍🧑")
                        if uf.verified_bot:
                            st.append("Verified Bot 👾")
                            is_bot = True
                        if uf.verified_bot_developer:
                            st.append("Verified Bot Developer 🏆")
                    if u.bot and not is_bot:
                        st.append("Bot 🤖")
                    if u.id == guild.owner_id and not hasattr(guild, "ghost"):
                        st.append("Server owner 👑")
                    if member:
                        dname = getattr(member, "nick", None)
                        joined = getattr(u, "joined_at", None)
                    else:
                        dname = getattr(u, "simulated", None) and getattr(u, "nick", None)
                        joined = None
                    created = u.created_at
                    if member:
                        rolelist = [role_mention(i.id) for i in reversed(getattr(u, "roles", ())) if not i.is_default()]
                        role = ", ".join(rolelist)
                    else:
                        role = None
                    seen = None
                    zone = None
                    with suppress(LookupError):
                        ts = utc()
                        ls = bot.data.users[u.id]["last_seen"]
                        la = bot.data.users[u.id].get("last_action")
                        if type(ls) is str:
                            seen = ls
                        else:
                            seen = f"{dyn_time_diff(ts, min(ts, ls))} ago"
                        if la:
                            seen = f"{la}, {seen}"
                        if "v" in flags:
                            tz = bot.data.users.estimate_timezone(u.id)
                            if tz >= 0:
                                zone = f"GMT+{tz}"
                            else:
                                zone = f"GMT{tz}"
                    if is_self and bot.webserver:
                        url2 = bot.webserver
                    else:
                        url2 = url
                    colour = await self.bot.get_colour(u)
                    emb = discord.Embed(colour=colour)
                    emb.set_thumbnail(url=url)
                    emb.set_author(name=name, icon_url=url, url=url2)
                    d = user_mention(u.id)
                    if st:
                        if d[-1] == "*":
                            d += " "
                        d += " **```css\n"
                        if st:
                            d += "\n".join(st)
                        d += "```**"
                    emb.description = d
                    emb.add_field(name="User ID", value="`" + str(u.id) + "`", inline=0)
                    emb.add_field(name="Creation time", value=str(created) + "\n" + dyn_time_diff(utc_dt().timestamp(), created.timestamp()) + " ago", inline=1)
                    if joined:
                        emb.add_field(name="Join time", value=str(joined) + "\n" + dyn_time_diff(utc_dt().timestamp(), joined.timestamp()) + " ago", inline=1)
                    if zone:
                        emb.add_field(name="Estimated timezone", value=str(zone), inline=1)
                    if seen:
                        emb.add_field(name="Last seen", value=str(seen), inline=1)
                    if dname:
                        emb.add_field(name="Nickname", value=dname, inline=1)
                    if role:
                        emb.add_field(name=f"Roles ({len(rolelist)})", value=role, inline=0)
                    embs.add(emb)
        bot.send_embeds(channel, embeds=embs)


class Profile(Command):
    name = ["User", "UserProfile"]
    description = "Shows or edits a user profile on ⟨MIZA⟩."
    usage = "(user|description|timezone|birthday)? <value>? <delete{?d}>?"
    flags = "d"
    rate_limit = 1
    no_parse = True
    slash = True
    usercmd = True

    async def __call__(self, user, args, argv, flags, channel, guild, bot, **void):
        setting = None
        if not args:
            target = user
        elif args[0] in ("description", "timezone", "time", "birthday"):
            target = user
            setting = args.pop(0)
            if not args:
                value = None
            else:
                value = argv[len(setting) + 1:]
        else:
            target = await bot.fetch_user_member(" ".join(args), guild)
        if setting is None:
            profile = bot.data.users.get(target.id, EMPTY)
            description = profile.get("description", "")
            birthday = profile.get("birthday")
            timezone = profile.get("timezone")
            if timezone:
                td = datetime.timedelta(seconds=as_timezone(timezone))
                description += ini_md(f"Current time: {sqr_md(utc_dt() + td)}")
            if birthday:
                if type(birthday) is not DynamicDT:
                    birthday = profile["birthday"] = DynamicDT.fromdatetime(birthday)
                    bot.data.users.update(target.id)
                t = utc_dt()
                if timezone:
                    birthday -= td
                description += ini_md(f"Age: {sqr_md(time_diff(t, birthday))}\nBirthday in: {sqr_md(time_diff(next_date(birthday), t))}")
            fields = set()
            for field in ("timezone", "birthday"):
                value = profile.get(field)
                if type(value) is DynamicDT:
                    value = value.as_date()
                elif field == "timezone" and value is not None:
                    value = timezone_repr(value)
                fields.add((field, value, False))
            return bot.send_as_embeds(channel, description, fields=fields, author=get_author(target))
        if value is None:
            return ini_md(f"Currently set {setting} for {sqr_md(user)}: {sqr_md(bot.data.users.get(user.id, EMPTY).get(setting))}.")
        if setting != "description" and value.casefold() in ("undefined", "remove", "rem", "reset", "unset", "delete", "clear", "null", "none") or "d" in flags:
            profile.pop(setting, None)
            bot.data.users.update(user.id)
            return css_md(f"Successfully removed {setting} for {sqr_md(user)}.")
        if setting == "description":
            if len(value) > 1024:
                raise OverflowError("Description must be 1024 or fewer in length.")
        elif setting.startswith("time"):
            value = value.casefold()
            try:
                as_timezone(value)
            except KeyError:
                raise ArgumentError(f"Entered value could not be recognized as a timezone location or abbreviation. Use {bot.get_prefix(guild)}timezone list for list.")
        else:
            dt = tzparse(value)
            offs, year = divmod(dt.year, 400)
            value = DynamicDT(year + 2000, dt.month, dt.day).set_offset(offs * 400 - 2000)
        bot.data.users.setdefault(user.id, {})[setting] = value
        bot.data.users.update(user.id)
        if type(value) is DynamicDT:
            value = value.as_date()
        elif setting.startswith("time") and value is not None:
            value = timezone_repr(value)
        return css_md(f"Successfully changed {setting} for {sqr_md(user)} to {sqr_md(value)}.")


class Activity(Command):
    name = ["Recent", "Log"]
    description = "Shows recent Discord activity for the targeted user, server, or channel."
    usage = "<user>? <verbose{?v}>?"
    flags="v"
    rate_limit = (2, 9)
    typing = True
    slash = True
    usercmd = True

    async def __call__(self, guild, user, argv, flags, channel, bot, _timeout, **void):
        u_id = None
        if argv:
            user = None
            if "#" not in argv:
                with suppress():
                    user = bot.cache.guilds[int(argv)]
            if user is None:
                try:
                    user = bot.cache.channels[verify_id(argv)]
                except:
                    user = await bot.fetch_user_member(argv, guild)
                else:
                    u_id = f"#{user.id}"
        if not u_id:
            u_id = user.id
        data = await create_future(bot.data.users.fetch_events, u_id, interval=max(900, 3600 >> flags.get("v", 0)), timeout=_timeout)
        with discord.context_managers.Typing(channel):
            resp = await process_image("plt_special", "$", (data, str(user)))
            fn = resp[0]
            f = CompatFile(fn, filename=f"{user.id}.png")
        return dict(file=f, filename=fn, best=True)


class Status(Command):
    name = ["State", "Ping"]
    description = "Shows the bot's current internal program state."
    usage = "(enable|disable)?"
    flags = "aed"
    slash = True

    async def __call__(self, perm, flags, channel, bot, **void):
        if "d" in flags:
            if perm < 2:
                raise PermissionError("Permission level 2 or higher required to unset auto-updating status.")
            bot.data.messages.pop(channel.id)
            bot.data.messages.update(channel.id)
            return fix_md("Successfully disabled status updates.")
        elif "a" not in flags and "e" not in flags:
            return await self._callback2_(channel)
        if perm < 2:
            raise PermissionError("Permission level 2 or higher required to set auto-updating status.")
        message = await channel.send(italics(code_md("Loading bot status...")))
        set_dict(bot.data.messages, channel.id, {})[message.id] = cdict(t=0, command="bot.commands.status[0]")
        bot.data.messages.update(channel.id)

    async def _callback2_(self, channel, m_id=None, msg=None, colour=None, **void):
        bot = self.bot
        if not hasattr(bot, "bitrate"):
            return
        emb = discord.Embed(colour=colour or rand_colour())
        url = await self.bot.get_proxy_url(self.bot.user)
        emb.set_author(name="Status", url=bot.webserver, icon_url=url)
        emb.timestamp = utc_dt()
        if msg is None:
            active = bot.get_active()
            try:
                shards = len(bot.latencies)
            except AttributeError:
                shards = 1
            size = sum(bot.size.values()) + sum(bot.size2.values())
            stats = bot.curr_state

            bot_info = (
                f"Process count\n`{active[0]}`\nThread count\n`{active[1]}`\nCoroutine count\n`{active[2]}`\n"
                + f"CPU usage\n`{round(stats[0], 3)}%`\nRAM usage\n`{byte_scale(stats[1])}B`\nDisk usage\n`{byte_scale(stats[2])}B`\nNetwork usage\n`{byte_scale(bot.bitrate)}bps`"
            )
            emb.add_field(name="Bot info", value=bot_info)

            discord_info = (
                f"Shard count\n`{shards}`\nServer count\n`{len(tuple(bot.cache.guilds.keys()))}`\nUser count\n`{len(tuple(bot.cache.users.keys()))}`\n"
                + f"Channel count\n`{len(tuple(bot.cache.channels.keys()))}`\nRole count\n`{len(tuple(bot.cache.roles.keys()))}`\nEmoji count\n`{len(tuple(bot.cache.emojis.keys()))}`\nCached messages\n`{len(bot.cache.messages)}`"
            )
            emb.add_field(name="Discord info", value=discord_info)

            misc_info = (
                f"Cached files\n`{bot.file_count}`\nConnected voice channels\n`{len(bot.audio.players)}`\nTotal data sent/received\n`{byte_scale(bot.total_bytes)}B`\n"
                + f"System time\n`{datetime.datetime.now()}`\nAPI latency\n`{sec2time(bot.api_latency)}`\nCurrent uptime\n`{dyn_time_diff(utc(), bot.start_time)}`\nActivity count since startup\n`{bot.activity}`"
            )
            emb.add_field(name="Misc info", value=misc_info)
            commands = set()
            for command in bot.commands.values():
                commands.update(command)
            code_info = (
                f"Code size\n[`{byte_scale(size[0])}B, {size[1]} lines`]({bot.github})\nCommand count\n[`{len(commands)}`](https://github.com/thomas-xin/Miza/wiki/Commands)\n"
                + f"Website URL\n[`{bot.webserver}`]({bot.webserver})"
            )
            emb.add_field(name="Code info", value=code_info)
        else:
            emb.description = msg
        func = channel.send
        if m_id is not None:
            with tracebacksuppressor(StopIteration, discord.NotFound, discord.Forbidden):
                message = bot.cache.messages.get(m_id)
                if message is None:
                    message = await aretry(channel.fetch_message, m_id, attempts=6, delay=2, exc=(discord.NotFound, discord.Forbidden))
                if message.id != channel.last_message_id:
                    async for m in bot.data.channel_cache.get(channel):
                        if message.id != m.id:
                            create_task(bot.silent_delete(message))
                            raise StopIteration
                        break
                func = lambda *args, **kwargs: message.edit(*args, content=None, **kwargs)
        message = await func(embed=emb)
        if m_id is not None and message is not None:
            bot.data.messages[channel.id] = {message.id: cdict(t=utc(), command="bot.commands.status[0]")}


class Invite(Command):
    name = ["Website", "BotInfo", "InviteLink"]
    description = "Sends a link to ⟨MIZA⟩'s homepage, github and invite code, as well as an invite link to the current server if applicable."
    slash = True

    async def __call__(self, channel, message, **void):
        emb = discord.Embed(colour=rand_colour())
        emb.set_author(**get_author(self.bot.user))
        emb.description = f"[**`My Github`**]({self.bot.github}) [**`My Website`**]({self.bot.webserver}) [**`My Invite`**]({self.bot.invite})"
        if message.guild:
            with tracebacksuppressor:
                member = message.guild.get_member(self.bot.id)
                if member.guild_permissions.create_instant_invite:
                    invites = await member.guild.invites()
                    invites = sorted(invites, key=lambda invite: (invite.max_age == 0, -abs(invite.max_uses - invite.uses), len(invite.url)))
                    if not invites:
                        c = self.bot.get_first_sendable(member.guild, member)
                        invite = await c.create_invite(reason="Invite command")
                    else:
                        invite = invites[0]
                    emb.description += f" [**`Server Invite`**]({invite.url})"
        self.bot.send_embeds(channel, embed=emb, reference=message)


class Upload(Command):
    name = ["Filehost"]
    description = "Sends a link to ⟨MIZA⟩'s webserver's upload page: ⟨WEBSERVER⟩/upload"
    msgcmd = True
    _timeout_ = 50

    async def __call__(self, message, argv, **void):
        if message.attachments:
            args.extend(best_url(a) for a in message.attachments)
            argv += " " * bool(argv) + " ".join(best_url(a) for a in message.attachments)
        args = await self.bot.follow_url(argv)
        if not args:
            return self.bot.webserver + "/upload"
        futs = deque()
        for url in args:
            futs.append(create_task(Request(self.bot.webserver + "/upload_url?url=" + url, decode=True, aio=True, timeout=1200)))
            await asyncio.sleep(0.1)
        out = deque()
        for fut in futs:
            url = await fut
            out.append(url)
        return "\n".join(out)


class Reminder(Command):
    name = ["Announcement", "Announcements", "Announce", "RemindMe", "Reminders", "Remind"]
    description = "Sets a reminder for a certain date and time."
    usage = "<1:message>? <0:time>? <urgent{?u}>? <delete{?d}>?"
    flags = "aedu"
    directions = [b'\xe2\x8f\xab', b'\xf0\x9f\x94\xbc', b'\xf0\x9f\x94\xbd', b'\xe2\x8f\xac', b'\xf0\x9f\x94\x84']
    dirnames = ["First", "Prev", "Next", "Last", "Refresh"]
    rate_limit = (1 / 3, 4)
    keywords = ["on", "at", "in", "when", "event"]
    keydict = {re.compile(f"(^|[^a-z0-9]){i[::-1]}([^a-z0-9]|$)", re.I): None for i in keywords}
    no_parse = True
    timefind = None
    slash = True

    def __load__(self):
        self.timefind = re.compile("(?:(?:(?:[0-9]+:)+[0-9.]+\\s*(?:am|pm)?|" + self.bot.num_words + "|[\\s\-+*\\/^%.,0-9]+\\s*(?:am|pm|s|m|h|d|w|y|century|centuries|millenium|millenia|(?:second|sec|minute|min|hour|hr|day|week|wk|month|mo|year|yr|decade|galactic[\\s\\-_]year)s?))\\s*)+$", re.I)

    async def __call__(self, name, message, flags, bot, user, guild, perm, argv, **void):
        msg = message.content
        try:
            msg = msg[msg.casefold().index(name) + len(name):]
        except ValueError:
            print_exc(msg)
            msg = msg.casefold().split(None, 1)[-1]
        orig = argv
        argv = msg.strip()
        args = argv.split()
        if "announce" in name:
            sendable = message.channel
            word = "announcements"
        else:
            sendable = user
            word = "reminders"
        rems = bot.data.reminders.get(sendable.id, [])
        update = bot.data.reminders.update
        if "d" in flags:
            if not len(rems):
                return ini_md(f"No {word} currently set for {sqr_md(sendable)}.")
            if not orig:
                i = 0
            else:
                i = await bot.eval_math(orig)
            i %= len(rems)
            x = rems.pop(i)
            if i == 0:
                with suppress(IndexError):
                    bot.data.reminders.listed.remove(sendable.id, key=lambda x: x[-1])
                if rems:
                    bot.data.reminders.listed.insort((rems[0]["t"], sendable.id), key=lambda x: x[0])
            update(sendable.id)
            return ini_md(f"Successfully removed {sqr_md(lim_str(x['msg'], 128))} from {word} list for {sqr_md(sendable)}.")
        if not argv:
            # Set callback message for scrollable list
            buttons = [cdict(emoji=dirn, name=name, custom_id=dirn) for dirn, name in zip(map(as_str, self.directions), self.dirnames)]
            await send_with_reply(
                None,
                message,
                "*```" + "\n" * ("z" in flags) + "callback-main-reminder-"
                + str(user.id) + "_0_" + str(sendable.id)
                + "-\nLoading Reminder database...```*",
                buttons=buttons,
            )
            return
        if len(rems) >= 64:
            raise OverflowError(f"You have reached the maximum of 64 {word}. Please remove one to add another.")
        for f in "aeu":
            if f in flags:
                for c in (f, f.upper()):
                    for q in "?-+":
                        argv = argv.replace(q + c + " ", "").replace(" " + q + c, "")
        urgent = "u" in flags
        recur = 60 if urgent else None
        remind_as = user
        # This parser is so unnecessarily long for what it does...
        keyed = False
        while True:
            temp = argv.casefold()
            if name == "remind" and temp.startswith("me "):
                argv = argv[3:]
                temp = argv.casefold()
            if temp.startswith("every ") and " " in argv[6:]:
                duration, argv = argv[6:].split(None, 1)
                recur = await bot.eval_time(duration)
                temp = argv.casefold()
            elif temp.startswith("urgently ") or temp.startswith("urgent "):
                argv = argv.split(None, 1)[1]
                temp = argv.casefold()
                recur = 60
                urgent = True
            if temp.startswith("as ") and " " in argv[3:]:
                query, argv = argv[3:].split(None, 1)
                remind_as = await self.bot.fetch_user_member(query, guild)
                temp = argv.casefold()
            if temp.startswith("to "):
                argv = argv[3:]
                temp = argv.casefold()
            elif temp.startswith("that "):
                argv = argv[5:]
                temp = argv.casefold()
            spl = None
            keywords = dict(self.keydict)
            # Reversed regex search
            temp2 = temp[::-1]
            for k in tuple(keywords):
                try:
                    i = re.search(k, temp2).end()
                    if not i:
                        raise ValueError
                except (ValueError, AttributeError):
                    keywords.pop(k)
                else:
                    keywords[k] = i
            # Sort found keywords by position
            indices = sorted(keywords, key=lambda k: keywords[k])
            if indices:
                foundkey = {self.keywords[tuple(self.keydict).index(indices[0])]: True}
            else:
                foundkey = cdict(get=lambda *void: None)
            if foundkey.get("event"):
                if " event " in argv:
                    spl = argv.rsplit(" event ", 1)
                elif temp.startswith("event "):
                    spl = [argv[6:]]
                    msg = ""
                if spl is not None:
                    msg = " event ".join(spl[:-1])
                    t = verify_id(spl[-1])
                    keyed = True
                    break
            if foundkey.get("when"):
                if temp.endswith("is online"):
                    argv = argv[:-9]
                if " when " in argv:
                    spl = argv.rsplit(" when ", 1)
                elif temp.startswith("when "):
                    spl = [argv[5:]]
                    msg = ""
                if spl is not None:
                    msg = " when ".join(spl[:-1])
                    t = verify_id(spl[-1])
                    keyed = True
                    break
            if foundkey.get("in"):
                if " in " in argv:
                    spl = argv.rsplit(" in ", 1)
                elif temp.startswith("in "):
                    spl = [argv[3:]]
                    msg = ""
                if spl is not None:
                    msg = " in ".join(spl[:-1])
                    t = await bot.eval_time(spl[-1])
                    break
            if foundkey.get("at"):
                if " at " in argv:
                    spl = argv.rsplit(" at ", 1)
                elif temp.startswith("at "):
                    spl = [argv[3:]]
                    msg = ""
                if spl is not None:
                    if len(spl) > 1:
                        spl2 = spl[0].rsplit(None, 1)
                        if spl2[-1] in ("today", "tomorrow", "yesterday"):
                            spl[0] = "" if len(spl2) <= 1 else spl2[0]
                            spl[-1] = "tomorrow " + spl[-1]
                    msg = " at ".join(spl[:-1])
                    t = utc_ts(tzparse(spl[-1])) - utc()
                    break
            if foundkey.get("on"):
                if " on " in argv:
                    spl = argv.rsplit(" on ", 1)
                elif temp.startswith("on "):
                    spl = [argv[3:]]
                    msg = ""
                if spl is not None:
                    msg = " on ".join(spl[:-1])
                    t = utc_ts(tzparse(spl[-1])) - utc()
                    break
            if "today" in argv or "tomorrow" in argv or "yesterday" in argv:
                t = 0
                if " " in argv:
                    args = argv.split()
                    for i in (0, -1):
                        arg = args[i]
                        with suppress(KeyError):
                            t = as_timezone(arg)
                            args.pop(i)
                            expr = " ".join(args)
                            break
                        h = 0
                    t += h * 3600
                match = re.search(self.timefind, argv)
                if match:
                    i = match.start()
                    spl = [argv[:i], argv[i:]]
                    msg = spl[0]
                    t += utc_ts(tzparse(spl[1])) - utc()
                    break
                msg = " ".join(args[:-1])
                t = utc_ts(tzparse(args[-1])) - utc()
                break
            t = 0
            if " " in argv:
                args = argv.split()
                for i in (0, -1):
                    arg = args[i]
                    with suppress(KeyError):
                        t = as_timezone(arg)
                        args.pop(i)
                        expr = " ".join(args)
                        break
                    h = 0
                t += h * 3600
            match = re.search(self.timefind, argv)
            if match:
                i = match.start()
                spl = [argv[:i], argv[i:]]
                msg = spl[0]
                t += await bot.eval_time(spl[1])
                break
            msg = " ".join(args[:-1])
            t = await bot.eval_time(args[-1])
            break
        if keyed:
            u = await bot.fetch_user_member(t, guild)
            t = u.id
        msg = msg.strip()
        if not msg:
            if "announce" in name:
                msg = "[SAMPLE ANNOUNCEMENT]"
            else:
                msg = "[SAMPLE REMINDER]"
            if urgent:
                msg = bold(css_md(msg, force=True))
            else:
                msg = bold(ini_md(msg))
        elif len(msg) > 4096:
            raise OverflowError(f"Input message too long ({len(msg)} > 4096).")
        username = str(remind_as)
        url = await bot.get_proxy_url(remind_as)
        ts = utc()
        if keyed:
            # Schedule for an event from a user
            rem = cdict(
                user=remind_as.id,
                msg=msg,
                u_id=t,
                t=inf,
            )
            rems.append(rem)
            s = "$" + str(t)
            seq = set_dict(bot.data.reminders, s, deque())
            seq.append(sendable.id)
            update(s)
        else:
            # Schedule for an event at a certain time
            rem = cdict(
                user=remind_as.id,
                msg=msg,
                t=t + ts,
            )
            rems.append(rem)
        if recur:
            rem.recur = recur
        # Sort list of reminders
        bot.data.reminders[sendable.id] = sort(rems, key=lambda x: x["t"])
        with suppress(IndexError):
            # Remove existing schedule
            bot.data.reminders.listed.remove(sendable.id, key=lambda x: x[-1])
        # Insert back into bot schedule
        tup = (bot.data.reminders[sendable.id][0]["t"], sendable.id)
        if is_finite(tup[0]):
            bot.data.reminders.listed.insort(tup, key=lambda x: x[0])
        update(sendable.id)
        emb = discord.Embed(description=msg)
        emb.colour = await bot.get_colour(remind_as)
        emb.set_author(name=username, url=url, icon_url=url)
        out = "```css\nSuccessfully set "
        if urgent:
            out += "urgent "
        if "announce" in name:
            out += f"announcement for {sqr_md(sendable)}"
        else:
            out += f"reminder for {sqr_md(sendable)}"
        if not urgent and recur:
            out += f" every {sqr_md(sec2time(recur))},"
        if keyed:
            out += f" upon next event from {sqr_md(user_mention(t))}"
        else:
            out += f" in {sqr_md(time_until(t + utc()))}"
        out += ":```"
        return dict(content=out, embed=emb)

    async def _callback_(self, bot, message, reaction, user, perm, vals, **void):
        u_id, pos, s_id = list(map(int, vals.split("_", 2)))
        if reaction not in (None, self.directions[-1]) and u_id != user.id:
            return
        if reaction not in self.directions and reaction is not None:
            return
        guild = message.guild
        user = await bot.fetch_user(u_id)
        rems = bot.data.reminders.get(s_id, [])
        sendable = await bot.fetch_messageable(s_id)
        page = 16
        last = max(0, len(rems) - page)
        if reaction is not None:
            i = self.directions.index(reaction)
            if i == 0:
                new = 0
            elif i == 1:
                new = max(0, pos - page)
            elif i == 2:
                new = min(last, pos + page)
            elif i == 3:
                new = last
            else:
                new = pos
            pos = new
        content = message.content
        if not content:
            content = message.embeds[0].description
        i = content.index("callback")
        content = "*```" + "\n" * ("\n" in content[:i]) + (
            "callback-main-reminder-"
            + str(u_id) + "_" + str(pos) + "_" + str(s_id)
            + "-\n"
        )
        if not rems:
            content += f"Schedule for {str(sendable).replace('`', '')} is currently empty.```*"
            msg = ""
        else:
            t = utc()
            content += f"{len(rems)} message{'s' if len(rems) != 1 else ''} currently scheduled for {str(sendable).replace('`', '')}:```*"
            msg = iter2str(
                rems[pos:pos + page],
                key=lambda x: lim_str(bot.get_user(x.get("user", -1), replace=True).mention + ": `" + no_md(x["msg"]), 96) + "` ➡️ " + (user_mention(x["u_id"]) if "u_id" in x else time_until(x["t"])),
                left="`[",
                right="]`",
            )
        colour = await self.bot.get_colour(user)
        emb = discord.Embed(
            description=content + msg,
            colour=colour,
        ).set_author(**get_author(user))
        more = len(rems) - pos - page
        if more > 0:
            emb.set_footer(text=f"{uni_str('And', 1)} {more} {uni_str('more...', 1)}")
        create_task(message.edit(content=None, embed=emb, allowed_mentions=discord.AllowedMentions.none()))
        if hasattr(message, "int_token"):
            await bot.ignore_interaction(message)


class UpdateUrgentReminders(Database):
    name = "urgentreminders"
    no_delete = True

    async def _bot_ready_(self, **void):
        if "listed" not in self.data:
            self.data["listed"] = alist()
        create_task(self.update_urgents())

    async def update_urgents(self):
        while True:
            with tracebacksuppressor:
                t = utc()
                listed = self.data["listed"]
                while listed:
                    p = listed[0]
                    if t < p[0]:
                        break
                    with suppress(StopIteration):
                        listed.popleft()
                        self.update("listed")
                        c_id = p[1]
                        m_id = p[2]
                        emb = p[3]
                        if len(p) < 4:
                            p.append(60)
                        i = 0
                        while p[0] < utc() + 1 and i < 4096:
                            p[0] += p[4]
                            i += 1
                        p[0] = max(utc() + 1, p[0])
                        channel = await self.bot.fetch_messageable(c_id)
                        message = await self.bot.fetch_message(m_id, channel)
                        for react in message.reactions:
                            if str(react) == "✅":
                                if react.count > 1:
                                    raise StopIteration
                                async for u in react.users():
                                    if u.id != self.bot.id:
                                        raise StopIteration
                        fut = create_task(channel.send(embed=emb))
                        await self.bot.silent_delete(message)
                        message = await fut
                        await message.add_reaction("✅")
                        p[2] = message.id
                        listed.insort(p, key=lambda x: x)
                        self.update("listed")
            await asyncio.sleep(1)


# This database is such a hassle to manage, it has to be able to persist between bot restarts, and has to be able to update with O(1) time complexity when idle
class UpdateReminders(Database):
    name = "reminders"
    no_delete = True

    def __load__(self):
        d = self.data
        # This exists so that checking next scheduled item is O(1)
        self.listed = alist(sorted(((d[i][0]["t"], i) for i in d if type(i) is not str and d[i]), key=lambda x: x[0]))

    async def recurrent_message(self, channel, embed, wait=60):
        t = utc()
        message = await channel.send(embed=embed)
        await message.add_reaction("✅")
        self.bot.data.urgentreminders.data["listed"].insort([t + wait, channel.id, message.id, embed, wait], key=lambda x: x)
        self.bot.data.urgentreminders.update()

    # Fast call: runs many times per second
    async def _call_(self):
        t = utc()
        while self.listed:
            p = self.listed[0]
            # Only check first item in the schedule
            if t < p[0]:
                break
            # Grab expired item
            self.listed.popleft()
            u_id = p[1]
            temp = self.data[u_id]
            if not temp:
                self.data.pop(u_id)
                continue
            # Check next item in schedule
            x = temp[0]
            if t < x["t"]:
                # Insert back into schedule if not expired
                self.listed.insort((x["t"], u_id), key=lambda x: x[0])
                print(self.listed)
                continue
            # Grab target from database
            x = cdict(temp.pop(0))
            self.update(u_id)
            if not temp:
                self.data.pop(u_id)
            else:
                # Insert next listed item into schedule
                self.listed.insort((temp[0]["t"], u_id), key=lambda x: x[0])
            # print(self.listed)
            # Send reminder to target user/channel
            ch = await self.bot.fetch_messageable(u_id)
            emb = discord.Embed(description=x.msg)
            try:
                u = self.bot.get_user(x["user"], replace=True)
            except KeyError:
                u = x
            emb.set_author(**get_author(u))
            if not x.get("recur"):
                self.bot.send_embeds(ch, emb)
            else:
                create_task(self.recurrent_message(ch, emb, x.get("recur", 60)))

    # Seen event: runs when users perform discord actions
    async def _seen_(self, user, **void):
        s = "$" + str(user.id)
        if s in self.data:
            assigned = self.data[s]
            # Ignore user events without assigned triggers
            if not assigned:
                self.data.pop(s)
                return
            with tracebacksuppressor:
                for u_id in assigned:
                    # Send reminder to all targeted users/channels
                    ch = await self.bot.fetch_messageable(u_id)
                    rems = set_dict(self.data, u_id, [])
                    pops = set()
                    for i, x in enumerate(reversed(rems), 1):
                        if x.get("u_id", None) == user.id:
                            emb = discord.Embed(description=x["msg"])
                            try:
                                u = self.bot.get_user(x["user"], replace=True)
                            except KeyError:
                                u = cdict(x)
                            emb.set_author(**get_author(u))
                            if not x.get("recur"):
                                self.bot.send_embeds(ch, emb)
                            else:
                                create_task(self.recurrent_message(ch, emb, x.get("recur", 60)))
                            pops.add(len(rems) - i)
                        elif is_finite(x["t"]):
                            break
                    it = [rems[i] for i in range(len(rems)) if i not in pops]
                    rems.clear()
                    rems.extend(it)
                    self.update(u_id)
                    if not rems:
                        self.data.pop(u_id)
            with suppress(KeyError):
                self.data.pop(s)      


class UpdatePrefix(Database):
    name = "prefixes"


class UpdateEnabled(Database):
    name = "enabled"
    no_delete = True


class UpdateMessages(Database):
    name = "messages"
    semaphore = Semaphore(80, 1, delay=1, rate_limit=16)
    closed = False
    hue = 0

    async def wrap_semaphore(self, func, *args, **kwargs):
        with tracebacksuppressor(SemaphoreOverflowError):
            async with self.semaphore:
                return await func(*args, **kwargs)

    async def __call__(self, **void):
        if self.bot.bot_ready and not self.closed:
            self.hue += 128
            col = colour2raw(hue2colour(self.hue))
            t = utc()
            for c_id, data in tuple(self.data.items()):
                with tracebacksuppressor():
                    try:
                        channel = await self.bot.fetch_channel(c_id)
                        if hasattr(channel, "guild") and channel.guild not in self.bot.guilds:
                            raise
                    except:
                        self.data.pop(c_id)
                    else:
                        for m_id, v in data.items():
                            if t - v.t >= 1:
                                v.t = t
                                create_task(self.wrap_semaphore(eval(v.command, self.bot._globals)._callback2_, channel=channel, m_id=m_id, colour=col))

    async def _destroy_(self, **void):
        self.closed = True
        self.hue += 128
        col = colour2raw(hue2colour(self.hue))
        msg = "Offline 😔"
        for c_id, data in self.data.items():
            with tracebacksuppressor(SemaphoreOverflowError):
                channel = await self.bot.fetch_channel(c_id)
                for m_id, v in data.items():
                    async with self.semaphore:
                        await eval(v.command, self.bot._globals)._callback2_(channel=channel, m_id=m_id, msg=msg, colour=col)



class UpdateFlavour(Database):
    name = "flavour"
    no_delete = True

    async def get(self):
        out = x = None
        i = xrand(7)
        facts = self.bot.data.users.facts
        questions = self.bot.data.users.questions
        useless = self.bot.data.users.useless
        if i < 2 and facts:
            with tracebacksuppressor:
                text = choice(facts)
                fact = choice(("Fun fact:", "Did you know?", "Useless fact:", "Random fact:"))
                out = f"\n{fact} `{text}`"
        elif i < 4 and questions:
            with tracebacksuppressor:
                text = choice(questions)
                out = f"\nRandom question: `{text}`"
        # elif i == 2:
        #     x = "affirmations"
        #     with tracebacksuppressor:
        #         if self.data.get(x) and len(self.data[x]) > 64 and xrand(2):
        #             return choice(self.data[x])
        #         data = await Request("https://www.affirmations.dev/", json=True, aio=True)
        #         text = data["affirmation"].replace("`", "")
        #         out = f"\nAffirmation: `{text}`"
        # elif i == 3:
        #     x = "geek_jokes"
        #     with tracebacksuppressor:
        #         if self.data.get(x) and len(self.data[x]) > 64 and xrand(2):
        #             return choice(self.data[x])
        #         data = await Request("https://geek-jokes.sameerkumar.website/api", json=True, aio=True)
        #         text = data.replace("`", "")
        #         out = f"\nGeek joke: `{text}`"
        else:
            x = "useless_facts"
            with tracebacksuppressor:
                if self.data.get(x) and len(self.data[x]) > 256 and xrand(2):
                    return choice(self.data[x])
                if len(useless) < 128 and (not useless or random.random() > 0.75):
                    data = await Request("https://www.uselessfacts.net/api/posts?d=" + str(datetime.datetime.fromtimestamp(xrand(1462456800, utc())).date()), json=True, aio=True)
                    factlist = [fact["title"].replace("`", "") for fact in data if "title" in fact]
                    random.shuffle(factlist)
                    useless.clear()
                    for text in factlist:
                        fact = choice(("Fun fact:", "Did you know?", "Useless fact:", "Random fact:"))
                        out = f"\n{fact} `{text}`"
                        useless.append(out)
                out = useless.popleft()
        if x and out:
            if x in self.data:
                if out not in self.data[x]:
                    self.data[x].add(out)
                    self.update(x)
            else:
                self.data[x] = alist((out,))
        return out


EMPTY = {}

# This database takes up a lot of space, storing so many events from users
class UpdateUsers(Database):
    name = "users"
    hours = 336
    interval = 900
    scale = 3600 // interval
    mentionspam = re.compile("<@[!&]?[0-9]+>")

    async def garbage_collect(self):
        for i in tuple(self.data):
            if type(i) is str:
                if i.startswith("#"):
                    c_id = int(i[1:].rstrip("\x7f"))
                    try:
                        await self.bot.fetch_channel(c_id)
                    except:
                        print(f"Deleting {i} from {self}...")
                        self.data.pop(i, None)
                        await asyncio.sleep(0.1)

    def __load__(self):
        self.semaphore = Semaphore(1, 2, delay=0.5)
        self.facts = None
        self.flavour_buffer = deque()
        self.flavour_set = set()
        self.flavour = ()
        self.useless = deque()
        with open("misc/facts.txt", "r", encoding="utf-8") as f:
            self.facts = f.read().splitlines()
        with open("misc/questions.txt", "r", encoding="utf-8") as f:
            self.questions = f.read().splitlines()
        with open("misc/r-questions.txt", "r", encoding="utf-8") as f:
            self.rquestions = f.read().splitlines()
        with open("misc/pickup_lines.txt", "r", encoding="utf-8") as f:
            self.pickup_lines = f.read().splitlines()
        with open("misc/nsfw_pickup_lines.txt", "r", encoding="utf-8") as f:
            self.nsfw_pickup_lines = f.read().splitlines()

    async def _bot_ready_(self, **void):
        data = {"Command": Command}
        exec(
            f"class {self.bot.name.replace(' ', '')}(Command):"
            + "\n\tdescription = 'Serves as an alias for mentioning the bot.'"
            + "\n\tno_parse = True"
            + "\n\tasync def __call__(self, message, argv, flags, **void):"
            + "\n\t\tawait self.bot.data.users._nocommand_(message, self.bot.user.mention + ' ' + argv, flags=flags, force=True)",
            data,
        )
        mod = "MAIN"
        for v in data.values():
            with suppress(TypeError):
                if issubclass(v, Command) and v != Command:
                    obj = v(self.bot, mod)
                    self.bot.categories[mod].append(obj)
                    # print(f"Successfully loaded command {repr(obj)}.")
        return await self()

    def clear_events(self, data, minimum):
        for hour in tuple(data):
            if hour > minimum:
                return
            data.pop(hour, None)

    def send_event(self, u_id, event, count=1):
        # print(self.bot.cache.users.get(u_id), event, count)
        data = set_dict(set_dict(self.data, u_id, {}), "recent", {})
        hour = round_min(int(utc() // self.interval) / self.scale)
        if data:
            self.clear_events(data, hour - self.hours)
        try:
            data[hour][event] += count
        except KeyError:
            try:
                data[hour][event] = count
            except KeyError:
                data[hour] = {event: count}

    fetch_events = lambda self, u_id, interval=3600: {i: self.get_events(u_id, interval=interval, event=i) for i in ("message", "typing", "command", "reaction", "misc")}

    # Get all events of a certain type from a certain user, with specified intervals.
    def get_events(self, u_id, interval=3600, event=None):
        data = self.data.get(u_id, EMPTY).get("recent")
        if not data:
            return list(repeat(0, int(self.hours / self.interval * interval)))
        hour = round_min(int(utc() // self.interval) / self.scale)
        self.clear_events(data, hour - self.hours)
        start = hour - self.hours
        if event is None:
            out = [np.sum(data.get(i / self.scale + start, EMPTY).values()) for i in range(self.hours * self.scale)]
        else:
            out = [data.get(i / self.scale + start, EMPTY).get(event, 0) for i in range(self.hours * self.scale)]
        if interval != self.interval:
            factor = ceil(interval / self.interval)
            out = [np.sum(out[i:i + factor]) for i in range(0, len(out), factor)]
        return out

    def get_timezone(self, u_id):
        timezone = self.data.get(u_id, EMPTY).get("timezone")
        if timezone is not None:
            return round_min(as_timezone(timezone) / 3600)

    def estimate_timezone(self, u_id):
        data = self.data.get(u_id, EMPTY).get("recent")
        if not data:
            return 0
        hour = round_min(int(utc() // self.interval) / self.scale)
        self.clear_events(data, hour - self.hours)
        start = hour - self.hours
        out = [sum(data.get(i / self.scale + start, EMPTY).values()) for i in range(self.hours * self.scale)]
        factor = ceil(3600 / self.interval)
        activity = [sum(out[i:i + factor]) for i in range(0, len(out), factor)]
        inactive = alist()
        def register(curr):
            if inactive:
                last = inactive[-1]
            if not inactive or curr[0] - last[0] >= 24:
                curr[1] += 1
                inactive.append(curr[:2])
                curr[2] = curr[0]
            elif curr[0] - last[0] - last[1] < 2:
                last[1] += curr[0] + curr[1] - last[0] - last[1]
                curr[2] = curr[0]
            elif last[1] <= curr[1] * 1.5:
                curr[1] += 1
                if curr[0] - curr[2] >= 18:
                    inactive.append(curr[:2])
                    curr[2] = curr[0]
                else:
                    inactive[-1] = curr[:2]
            curr[0] = None
            curr[1] = 0
        m = min(activity) * 4
        curr = [None, 0, 0]
        for i, x in enumerate(activity):
            if x <= m:
                if curr[0] is None:
                    curr[0] = i
                curr[1] += 1
            else:
                if curr[0] is not None:
                    register(curr)
        if curr[0] is not None:
            register(curr)
        total = 0
        if inactive:
            for i, curr in enumerate(inactive):
                t = (curr[0] + curr[1] / 2) % 24
                if i:
                    if total / i - t > 12:
                        total += 24
                    elif total / i - t < -12:
                        total -= 24
                total += t
            estimated = round(2.5 - utc_dt().hour - total / len(inactive)) % 24
            if estimated > 12:
                estimated -= 24
        else:
            estimated = 0
        # print(estimated, inactive, activity)
        return estimated

    async def __call__(self):
        with suppress(SemaphoreOverflowError):
            async with self.semaphore:
                changed = False
                while len(self.flavour_buffer) < 32:
                    out = await self.bot.data.flavour.get()
                    if out:
                        self.flavour_buffer.append(out)
                        self.flavour_set.add(out)
                        changed = True
                amount = len(self.flavour_set)
                if changed and (not amount & amount - 1):
                    self.flavour = tuple(self.flavour_set)

    def _offline_(self, user, **void):
        set_dict(self.data, user.id, {})["last_offline"] = utc()
        self.update(user.id)

    # User seen, add event to activity database
    def _seen_(self, user, delay, event, count=1, raw=None, **void):
        if is_channel(user):
            u_id = "#" + str(user.id)
        else:
            u_id = user.id
        self.send_event(u_id, event, count=count)
        if type(user) in (discord.User, discord.Member):
            add_dict(self.data, {u_id: {"last_seen": 0}})
            self.data[u_id]["last_seen"] = utc() + delay
            self.data[u_id]["last_action"] = raw
        self.update(u_id)

    # User executed command, add to activity database
    def _command_(self, user, loop, command, **void):
        self.send_event(user.id, "command")
        add_dict(self.data, {user.id: {"commands": {command.parse_name(): 1}}})
        self.data[user.id]["last_used"] = utc()
        self.data.get(user.id, EMPTY).pop("last_mention", None)
        if not loop:
            self.add_xp(user, getattr(command, "xp", xrand(6, 14)))

    async def react_sparkle(self, message):
        bot = self.bot
        react = await create_future(bot.data.emojis.get, "sparkles.gif")
        return await message.add_reaction(react)

    def _send_(self, message, **void):
        user = message.author
        if user.id == self.bot.id or self.bot.get_perms(user, message.guild) <= -inf:
            return
        size = get_message_length(message)
        points = math.sqrt(size) + sum(1 for w in message.content.split() if len(w) > 1)
        if points >= 32 and not message.attachments:
            typing = self.data.get(user.id, EMPTY).get("last_typing", None)
            if typing is None:
                set_dict(self.data, user.id, {})["last_typing"] = inf
            elif typing >= inf:
                return
            else:
                self.data.get(user.id, EMPTY).pop("last_typing", None)
        else:
            self.data.get(user.id, EMPTY).pop("last_typing", None)
        if not xrand(1000):
            self.add_diamonds(user, points)
            points *= 1000
            # create_task(message.add_reaction("✨"))
            if self.bot.data.enabled.get(message.channel.id, True):
                create_task(self.react_sparkle(message))
            print(f"{user} has triggered the rare message bonus in {message.guild}!")
        else:
            self.add_gold(user, points)
        self.add_xp(user, points)
        if "dailies" in self.bot.data:
            create_task(self.bot.data.dailies.valid_message(message))

    async def _mention_(self, user, message, msg, **void):
        bot = self.bot
        mentions = self.mentionspam.findall(msg)
        t = utc()
        out = None
        if len(mentions) >= xrand(8, 12) and self.data.get(user.id, EMPTY).get("last_mention", 0) > 3:
            out = f"{choice('🥴😣😪😢')} please calm down a second, I'm only here to help..."
        elif len(mentions) >= 3 and (self.data.get(user.id, EMPTY).get("last_mention", 0) > 2 or random.random() >= 2 / 3):
            out = f"{choice('😟😦😓')} oh, that's a lot of mentions, is everything okay?"
        elif len(mentions) >= 2 and self.data.get(user.id, EMPTY).get("last_mention", 0) > 0 and random.random() >= 0.75:
            out = "One mention is enough, but I appreciate your enthusiasm 🙂"
        if out:
            create_task(send_with_react(message.channel, out, reacts="❎", reference=message))
            await bot.seen(user, event="misc", raw="Being naughty")
            add_dict(self.data, {user.id: {"last_mention": 1}})
            self.data[user.id]["last_used"] = t
            self.update(user.id)
            raise CommandCancelledError

    def get_xp(self, user):
        if self.bot.is_blacklisted(user.id):
            return -inf
        if user.id == self.bot.id:
            if self.data.get(self.bot.id, EMPTY).get("xp", 0) != inf:
                set_dict(self.data, self.bot.id, {})["xp"] = inf
                self.data[self.bot.id]["gold"] = inf
                self.data[self.bot.id]["diamonds"] = inf
                self.update(self.bot.id)
            return inf
        return self.data.get(user.id, EMPTY).get("xp", 0)

    def xp_to_level(self, xp):
        if is_finite(xp):
            return int((xp * 3 / 2000) ** (2 / 3)) + 1
        return xp

    def xp_to_next(self, level):
        if is_finite(level):
            return ceil(math.sqrt(level - 1) * 1000)
        return level

    def xp_required(self, level):
        if is_finite(level):
            return ceil((level - 1) ** 1.5 * 2000 / 3)
        return level

    async def get_balance(self, user):
        data = self.data.get(user.id, EMPTY)
        return await self.bot.as_rewards(data.get("diamonds"), data.get("gold"))

    def add_xp(self, user, amount):
        if user.id != self.bot.id and amount and not self.bot.is_blacklisted(user.id):
            add_dict(set_dict(self.data, user.id, {}), {"xp": amount})
            if "dailies" in self.bot.data:
                self.bot.data.dailies.progress_quests(user, "xp", amount)
            self.update(user.id)

    def add_gold(self, user, amount):
        if user.id != self.bot.id and amount and not self.bot.is_blacklisted(user.id):
            add_dict(set_dict(self.data, user.id, {}), {"gold": amount})
            self.update(user.id)

    def add_diamonds(self, user, amount):
        if user.id != self.bot.id and amount and not self.bot.is_blacklisted(user.id):
            add_dict(set_dict(self.data, user.id, {}), {"diamonds": amount})
            if "dailies" in self.bot.data:
                self.bot.data.dailies.progress_quests(user, "diamond", amount)
            self.update(user.id)

    async def _typing_(self, user, **void):
        set_dict(self.data, user.id, {})["last_typing"] = utc()
        self.update(user.id)

    async def _nocommand_(self, message, msg, force=False, flags=(), truemention=True, **void):
        bot = self.bot
        user = message.author
        # Smudge invaded this code to mimic the funny mishaps from Eliza AI
        if message.content.startswith("The trouble is, my mother's "):
            await send_with_reply(message.channel, message, f"How long has she been {message.content[28:]}?")
            return

        if force or truemention and bot.is_mentioned(message, bot, message.guild):
            if user.bot:
                with suppress(AttributeError):
                    async for m in self.bot.data.channel_cache.get(message.channel):
                        user = m.author
                        if bot.get_perms(user.id, message.guild) <= -inf:
                            return
                        if not user.bot:
                            break
            send = lambda *args, **kwargs: send_with_reply(message.channel, not flags and message, *args, **kwargs)
            out = None
            count = self.data.get(user.id, EMPTY).get("last_talk", 0)
            # Simulates a randomized conversation
            if count < 5:
                create_task(message.add_reaction("👀"))
            if "?" in msg and "ask" in bot.commands and random.random() > math.atan(count / 16) / 4:
                argv = self.mentionspam.sub("", msg).strip()
                for ask in bot.commands.ask:
                    await ask(message, message.channel, user, argv, name="ask", flags=flags)
                return
            if count:
                if count < 2 or count == 2 and xrand(2):
                    # Starts conversations
                    out = choice(
                        f"So, {user.display_name}, how's your day been?",
                        f"How do you do, {user.name}?",
                        f"How are you today, {user.name}?",
                        "What's up?",
                        "Can I entertain you with a little something today?",
                    )
                elif count < 16 or random.random() > math.atan(max(0, count / 8 - 3)) / 4:
                    # General messages
                    if (count < 6 or self.mentionspam.sub("", msg).strip()) and random.random() < 0.5:
                        out = choice((f"'sup, {user.display_name}?", f"There you are, {user.name}!", "Oh yeah!", "👋", f"Hey, {user.display_name}!"))
                    else:
                        out = ""
                elif count < 24:
                    # Occasional late message
                    if random.random() < 0.4:
                        out = choice(
                            "You seem rather bored... I may only be as good as my programming allows me to be, but I'll try my best to fix that! 🎆",
                            "You must be bored, allow me to entertain you! 🍿",
                        )
                    else:
                        out = ""
                else:
                    # Late conversation messages
                    out = choice(
                        "It's been a fun conversation, but don't you have anything better to do? 🌞",
                        "This is what I was made for, I can do it forever, but you're only a human, take a break! 😅",
                        f"Woah, have you checked the time? We've been talking for {count + 1} messages! 😮"
                    )
            elif utc() - self.data.get(user.id, EMPTY).get("last_used", inf) >= 259200:
                # Triggers for users not seen in 3 days or longer
                out = choice((f"Long time no see, {user.name}!", f"Great to see you again, {user.display_name}!", f"It's been a while, {user.name}!"))
            if out is not None:
                guild = message.guild
                # Add randomized flavour text if in conversation
                if not xrand(4):
                    front = choice(
                        "Random question",
                        "Question for you",
                        "Conversation starter",
                    )
                    out += f"\n{front}: `{choice(self.questions)}`"
                elif self.flavour_buffer:
                    out += self.flavour_buffer.popleft()
                else:
                    out += choice(self.flavour)
            else:
                # Help message greetings
                i = xrand(7)
                if i == 0:
                    out = "I have been summoned!"
                elif i == 1:
                    out = f"Hey there! Name's {bot.name}!"
                elif i == 2:
                    out = f"Hello {user.name}, nice to see you! Can I help you?"
                elif i == 3:
                    out = f"Howdy, {user.display_name}!"
                elif i == 4:
                    out = f"Greetings, {user.name}! May I be of service?"
                elif i == 5:
                    out = f"Hi, {user.name}! What can I do for you today?"
                else:
                    out = f"Yo, what's good, {user.display_name}? Need me for anything?"
                prefix = bot.get_prefix(message.guild)
                out += f" Use `{prefix}help` or `/help` for help!"
                send = lambda *args, **kwargs: send_with_react(message.channel, *args, reacts="❎", reference=not flags and message, **kwargs)
            add_dict(self.data, {user.id: {"last_talk": 1, "last_mention": 1}})
            self.data[user.id]["last_used"] = utc()
            await send(out)
            await bot.seen(user, event="misc", raw="Talking to me")
            self.add_xp(user, xrand(12, 20))
            if "dailies" in bot.data:
                bot.data.dailies.progress_quests(user, "talk")
        else:
            if not self.data.get(user.id, EMPTY).get("last_mention") and random.random() > 0.6:
                self.data.get(user.id, EMPTY).pop("last_talk", None)
            self.data.get(user.id, EMPTY).pop("last_mention", None)
        self.update(user.id)