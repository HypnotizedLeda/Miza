print = PRINT

import csv, knackpy
from prettytable import PrettyTable as ptable


class DouClub:

    def __init__(self, c_id, c_sec):
        self.id = c_id
        self.secret = c_sec
        self.time = utc()
        self.knack = knackpy.App(app_id=self.id, api_key=self.secret)
        create_future_ex(self.pull)

    def pull(self):
        with tracebacksuppressor:
            # print("Pulling Doukutsu Club...")
            self.data = self.knack.get("object_1")
            self.time = utc()

    def update(self):
        if utc() - self.time > 720:
            create_future_ex(self.pull, timeout=60)
            self.time = utc()

    def search(self, query):
        # This string search algorithm could be better
        output = []
        query = query.casefold()
        for l in self.data:
            found = True
            qlist = set(query.split())
            for q in qlist:
                tag = False
                for k in l:
                    i = str(l[k])
                    if q in i.casefold():
                        tag = True
                        break
                if not tag:
                    found = False
                    break
            if found:
                output.append({
                    "author": l["Author"]["identifierdata[0]['title'"],
                    "name": l["Title"],
                    "description": l["Description"],
                    "url": (
                        "https://doukutsuclub.knack.com/database#search-database/mod-details/"
                        + l["id"] + "/"
                    ),
                })
        return output

try:
    douclub = DouClub(AUTH["knack_id"], AUTH["knack_secret"])
except KeyError:
    douclub = cdict(
        search=lambda *void1, **void2: exec('raise FileNotFoundError("Unable to search Doukutsu Club.")'),
        update=lambda: None
    )
    print("WARNING: knack_id/knack_secret not found. Unable to search Doukutsu Club.")


async def searchForums(query):
    url = (
        "https://www.cavestory.org/forums/search/1/?q=" + query.replace(" ", "+")
        + "&t=post&c[child_nodes]=1&c[nodes][0]=33&o=date&g=1"
    )
    s = await Request(url, aio=True, timeout=16, decode=True)
    output = []
    i = 0
    while i < len(s):
        # HTML is a mess
        try:
            search = '<li class="block-row block-row--separated  js-inlineModContainer" data-author="'
            s = s[s.index(search) + len(search):]
        except ValueError:
            break
        j = s.index('">')
        curr = {"author": s[:j]}
        s = s[s.index('<h3 class="contentRow-title">'):]
        search = '<a href="/forums/'
        s = s[s.index(search) + len(search):]
        j = s.index('">')
        curr["url"] = 'https://www.cavestory.org/forums/' + s[:j]
        s = s[j + 2:]
        j = s.index('</a>')
        curr["name"] = s[:j]
        search = '<div class="contentRow-snippet">'
        s = s[s.index(search) + len(search):]
        j = s.index('</div>')
        curr["description"] = s[:j]
        for elem in curr:
            temp = curr[elem].replace('<em class="textHighlight">', "").replace('</em>', "")
            temp = html_decode(temp)
            curr[elem] = temp
        output.append(curr)
    return output


class SheetPull:

    def __init__(self, url):
        self.url = url
        self.time = utc()
        create_future_ex(self.pull)

    def update(self):
        if utc() - self.time > 720:
            create_future_ex(self.pull, timeout=60)
            self.time = utc()

    def pull(self):
        with tracebacksuppressor:
            # print("Pulling Spreadsheet...")
            url = self.url
            text = Request(url, timeout=32, decode=True)
            data = text.split("\r\n")
            columns = 0
            sdata = [[], utc()]
            # Splits rows and colums into cells
            for i in range(len(data)):
                line = data[i]
                read = list(csv.reader(line))
                reli = []
                curr = ""
                for j in read:
                    if len(j) >= 2 and j[0] == j[1] == "":
                        if curr != "":
                            reli.append(curr)
                            curr = ""
                    else:
                        curr += "".join(j)
                if curr != "":
                    reli.append(curr)
                if len(reli):
                    columns = max(columns, len(reli))
                    sdata[0].append(reli)
                for line in range(len(sdata[0])):
                    while len(sdata[0][line]) < columns:
                        sdata[0][line].append(" ")
            self.data = sdata
            self.time = utc()

    def search(self, query, lim):
        output = []
        query = query.casefold()
        try:
            int(query)
            mode = 0
        except ValueError:
            mode = 1
        if not mode:
            for l in self.data[0]:
                if l[0] == query:
                    temp = [lim_line(e, lim) for e in l]
                    output.append(temp)
        else:
            qlist = set(query.split())
            for l in self.data[0]:
                if len(l) >= 3:
                    found = True
                    for q in qlist:
                        tag = False
                        for i in l:
                            if q in i.casefold():
                                tag = True
                                break
                        if not tag:
                            found = False
                            break
                    if found:
                        temp = [lim_line(e, lim) for e in l]
                        if temp[2].replace(" ", ""):
                            output.append(temp)
        return output


# URLs of Google Sheets .csv download links
entity_list = SheetPull(
    "https://docs.google.com/spreadsheets/d/12iC9uRGNZ2MnrhpS4s_KvIRYHhC56mPXCnCcsDjxit0\
/export?format=csv&id=12iC9uRGNZ2MnrhpS4s_KvIRYHhC56mPXCnCcsDjxit0&gid=0"
)
tsc_list = SheetPull(
    "https://docs.google.com/spreadsheets/d/11LL7T_jDPcWuhkJycsEoBGa9i-rjRjgMW04Gdz9EO6U\
/export?format=csv&id=11LL7T_jDPcWuhkJycsEoBGa9i-rjRjgMW04Gdz9EO6U&gid=0"
)


# Flag calculation algorithms

def _n2f(n):
    flag = int(n)
    offset = max(0, (999 - flag) // 1000)
    flag += offset * 1000
    output = ""
    for i in range(0, 3):
        a = 10 ** i
        b = flag // a
        char = b % 10
        char += 48
        output += chr(char)
    char = flag // 1000
    char += 48
    char -= offset
    try:
        return chr(char) + output[::-1]
    except ValueError:
        return "(0x" + hex((char + 256) & 255).upper()[2:] + ")" + output[::-1]

def _m2f(mem, val):
    val1 = mem
    val2 = val & 4294967295
    curr = 0
    result = ""
    for _ in loop(32):
        difference = int(val1, 16) - 4840864 + curr / 8
        flag = difference * 8
        output = _n2f(flag)
        if val2 & 1:
            operation = "+"
        else:
            operation = "-"
        output = "<FL" + operation + output
        result += output
        val2 >>= 1
        curr += 1
    return result


class CS_mem2flag(Command):
    name = ["CS_m2f"]
    description = "Returns a sequence of Cave Story TSC commands to set a certain memory address to a certain value."
    usage = "<0:address> <1:value(1)>?"
    rate_limit = 1

    async def __call__(self, bot, args, user, **void):
        if len(args) < 2:
            num = 1
        else:
            num = await bot.eval_math(" ".join(args[1:]))
        return css_md(_m2f(args[0], num))


class CS_hex2xml(Command):
    time_consuming = True
    name = ["CS_h2x"]
    description = "Converts a given Cave Story hex patch to an xml file readable by Booster's Lab."
    usage = "<hex_data>"
    rate_limit = (3, 5)

    async def __call__(self, bot, argv, channel, message, **void):
        hacks = {}
        hack = argv.replace(" ", "").replace("`", "").strip("\n")
        while len(hack):
            # hack XML parser
            try:
                i = hack.index("0x")
            except ValueError:
                break
            hack = hack[i:]
            i = hack.index("\n")
            offs = hack[:i]
            hack = hack[i + 1:]
            try:
                i = hack.index("0x")
                curr = hack[:i]
                hack = hack[i:]
            except ValueError:
                curr = hack
                hack = ""
            curr = curr.replace(" ", "").replace("\n", "").replace("\r", "")
            n = 2
            curr = " ".join([curr[i:i + n] for i in range(0, len(curr), n)])
            if offs in hacks:
                hacks[offs] = curr + hacks[offs][len(curr):]
            else:
                hacks[offs] = curr
        # Generate hack template
        output = (
            '<?xml version="1.0" encoding="UTF-8"?>\n<hack name="HEX PATCH">\n'
            + '\t<panel>\n'
            + '\t\t<panel title="Description">\n'
            + '\t\t</panel>\n'
            + '\t\t<field type="info">\n'
            + '\t\t\tHex patch converted by ' + bot.user.name + '.\n'
            + '\t\t</field>\n'
            + '\t\t<panel title="Data">\n'
            + '\t\t</panel>\n'
            + '\t\t<panel>\n'
        )
        col = 0
        for hack in sorted(hacks):
            n = 63
            p = hacks[hack]
            p = '\n\t\t\t\t'.join([p[i:i + n] for i in range(0, len(p), n)])
            output += (
                '\t\t\t<field type="data" offset="' + hack + '" col="' + str(col) + '">\n'
                + '\t\t\t\t' + p + '\n'
                + '\t\t\t</field>\n'
            )
            col = 1 + col & 3
        output += (
            '\t\t</panel>\n'
            + '\t</panel>\n'
            + '</hack>'
        )
        # This probably doesn't need to run concurrently
        data = await create_future(bytes, output, "utf-8", timeout=8)
        b = io.BytesIO(data)
        f = CompatFile(b, filename="patch.xml")
        create_task(bot.send_with_file(channel, "Patch successfully converted!", f, reference=message))


class CS_npc(Command):
    time_consuming = True
    description = "Searches the Cave Story NPC list for an NPC by name or ID."
    usage = "<query> <condensed{?c}>?"
    flags = "c"
    no_parse = True
    rate_limit = 2

    async def __call__(self, bot, args, flags, **void):
        lim = ("c" not in flags) * 40 + 20
        argv = " ".join(args)
        data = await create_future(entity_list.search, argv, lim, timeout=8)
        # Sends multiple messages up to 20000 characters total
        if len(data):
            head = entity_list.data[0][1]
            for i in range(len(head)):
                if head[i] == "":
                    head[i] = i * " "
            table = ptable(head)
            for line in data:
                table.add_row(line)
            output = str(table)
            if len(output) < 20000 and len(output) > 1900:
                response = [f"Search results for `{argv}`:"]
                lines = output.splitlines()
                curr = "```\n"
                for line in lines:
                    if len(curr) + len(line) > 1900:
                        response.append(curr + "```")
                        curr = "```\n"
                    if len(line):
                        curr += line + "\n"
                response.append(curr + "```")
                return response
            return f"Search results for `{argv}`:\n{code_md(output)}"
        raise LookupError(f"No results for {argv}.")


class CS_tsc(Command):
    description = "Searches the Cave Story OOB flags list for a memory variable."
    usage = "<query> <condensed{?c}>?"
    flags = "c"
    no_parse = True
    rate_limit = 2

    async def __call__(self, args, flags, **void):
        lim = ("c" not in flags) * 40 + 20
        argv = " ".join(args)
        data = await create_future(tsc_list.search, argv, lim, timeout=8)
        # Sends multiple messages up to 20000 characters total
        if len(data):
            head = tsc_list.data[0][0]
            for i in range(len(head)):
                if head[i] == "":
                    head[i] = i * " "
            table = ptable(head)
            for line in data:
                table.add_row(line)
            output = str(table)
            if len(output) < 20000 and len(output) > 1900:
                response = [f"Search results for `{argv}`:"]
                lines = output.splitlines()
                curr = "```\n"
                for line in lines:
                    if len(curr) + len(line) > 1900:
                        response.append(curr + "```")
                        curr = "```\n"
                    if len(line):
                        curr += line + "\n"
                response.append(curr + "```")
                return response
            return f"Search results for `{argv}`:\n{code_md(output)}"
        raise LookupError(f"No results for {argv}.")


class CS_mod(Command):
    time_consuming = True
    name = ["CS_search"]
    description = "Searches the Doukutsu Club and Cave Story Tribute Site Forums for an item."
    usage = "<query>"
    no_parse = True
    rate_limit = (3, 7)

    async def __call__(self, args, **void):
        argv = " ".join(args)
        data = await searchForums(argv)
        data += await create_future(douclub.search, argv, timeout=8)
        # Sends multiple messages up to 20000 characters total
        if len(data):
            response = f"Search results for `{argv}`:\n"
            for l in data:
                line = (
                    "\n<" + str(l["url"]) + ">\n"
                    + "```css\nName: [" + no_md(l["name"])
                    + "]\nAuthor: [" + no_md(l["author"].strip(" "))
                    + "]\n" + lim_str(l["description"].replace("\n", " "), 128)
                    + "```\r"
                )
                response += line
            if len(response) < 20000 and len(response) > 1900:
                output = response.split("\r")
                response = []
                curr = ""
                for line in output:
                    if len(curr) + len(line) > 1900:
                        response.append(curr)
                        curr = line
                    else:
                        curr += line
            return response
        raise LookupError(f"No results for {argv}.")


class CS_Database(Database):
    name = "cs_database"
    no_file = True

    async def __call__(self, **void):
        entity_list.update()
        tsc_list.update()
        douclub.update()


class MathQuiz(Command):
    name = ["MathTest", "MQ"]
    min_level = 1
    description = "Starts a math quiz in the current channel."
    usage = "(easy|hard)? <disable{?d}>?"
    flags = "aed"
    rate_limit = 3

    async def __call__(self, channel, guild, flags, argv, **void):
        mathdb = self.bot.data.mathtest
        if "d" in flags:
            if channel.id in mathdb.data:
                mathdb.data.pop(channel.id)
            return italics(css_md(f"Disabled math quizzes for {sqr_md(channel)}."))
        if not argv:
            argv = "easy"
        elif argv not in ("easy", "hard"):
            raise TypeError("Invalid quiz mode.")
        mathdb.data[channel.id] = cdict(mode=argv, answer=None)
        return italics(css_md(f"Enabled {argv} math quiz for {sqr_md(channel)}."))


class UpdateMathTest(Database):
    name = "mathtest"
    no_file = True

    def __load__(self):
        s = "⁰¹²³⁴⁵⁶⁷⁸⁹"
        ss = {str(i): s[i] for i in range(len(s))}
        ss["-"] = "⁻"
        self.sst = "".maketrans(ss)

    def format(self, x, y, op):
        length = 6
        xs = str(x)
        xs = " " * (length - len(xs)) + xs
        ys = str(y)
        ys = " " * (length - len(ys)) + ys
        return " " + xs + "\n" + op + ys

    def eqtrans(self, eq):
        return str(eq).replace("**", "^").replace("exp", "e^").replace("*", "∙")

    # Addition of 2 numbers less than 10000
    def addition(self):
        x = xrand(10000)
        y = xrand(10000)
        s = self.format(x, y, "+")
        return s, x + y

    # Subtraction of 2 numbers, result must be greater than or equal to 0
    def subtraction(self):
        x = xrand(12000)
        y = xrand(8000)
        if x < y:
            x, y = y, x
        s = self.format(x, y, "-")
        return s, x - y

    # Addition of 2 numbers 2~20
    def multiplication(self):
        x = xrand(2, 20)
        y = xrand(2, 20)
        s = self.format(x, y, "×")
        return s, x * y

    # Addition of 2 numbers 13~99
    def multiplication2(self):
        x = xrand(13, 100)
        y = xrand(13, 100)
        s = self.format(x, y, "×")
        return s, x * y

    # Division result between 2 and 13
    def division(self):
        y = xrand(2, 20)
        x = xrand(2, 14) * y
        s = self.format(x, y, "/")
        return s, x // y

    # Power of 2
    def exponentiation(self):
        x = xrand(2, 20)
        y = xrand(2, max(3, 14 / x))
        s = str(x) + "^" + str(y)
        return s, x ** y

    # Power of 2 or 3
    def exponentiation2(self):
        x = xrand(2, 4)
        if x == 2:
            y = xrand(7, 35)
        else:
            y = xrand(5, 11)
        s = str(x) + "^" + str(y)
        return s, x ** y

    # Square root result between 2 and 19
    def square_root(self):
        x = xrand(2, 20)
        y = x ** 2
        s = "√" + str(y)
        return s, x

    # Square root result between 21 and 99
    def square_root2(self):
        x = xrand(21, 1000)
        y = x ** 2
        s = "√" + str(y)
        return s, x

    # Scientific number form, exponent between -3 and 5
    def scientific(self):
        x = xrand(100, 10000)
        x /= 10 ** int(math.log10(x))
        y = xrand(-3, 6)
        s = str(x) + "×10^" + str(y)
        return s, round(x * 10 ** y, 9)

    # Like division but may result in a finite decimal
    def fraction(self):
        y = choice([2, 4, 5, 10])
        x = xrand(3, 20)
        mult = xrand(4) + 1
        y *= mult
        x *= mult
        s = self.format(x, y, "/")
        return s, round(x / y, 9)

    # An infinite recurring decimal number of up to 3 digits
    def recurring(self):
        x = "".join(str(xrand(10)) for _ in loop(xrand(2, 4)))
        s = "0." + "".join(x[i % len(x)] for i in range(28)) + "..."
        ans = "0.[" + x + "]"
        return s, ans

    # Quadratic equation with a = 1
    def equation(self):
        a = xrand(1, 10)
        b = xrand(1, 10)
        if xrand(2):
            a = -a
        if xrand(2):
            b = -b
        bx = -a - b
        cx = a * b
        s = "x^2 "
        if bx:
            s += ("+", "-")[bx < 0] + " " + (str(abs(bx))) * (abs(bx) != 1) +  "x "
        s += ("+", "-")[cx < 0] + " " + str(abs(cx)) + " = 0"
        return s, [a, b]

    # Quadratic equation with all values up to 13
    async def equation2(self):
        a = xrand(1, 14)
        b = xrand(1, 14)
        c = xrand(1, 14)
        d = xrand(1, 14)
        if xrand(2):
            a = -a
        if xrand(2):
            b = -b
        if xrand(2):
            c = -c
        if xrand(2):
            d = -d
        st = "(" + str(a) + "*x+" + str(b) + ")*(" + str(c) + "*x+" + str(d) + ")"
        a = [-sympy.Number(b) / a, -sympy.Number(d) / c]
        q = await create_future(sympy.expand, st, timeout=8)
        q = self.eqtrans(q).replace("∙", "") + " = 0"
        return q, a

    # A derivative or integral
    async def calculus(self):
        amount = xrand(2, 5)
        s = []
        for i in range(amount):
            t = xrand(3)
            if t == 0:
                a = xrand(1, 7)
                e = xrand(-3, 8)
                if xrand(2):
                    a = -a
                s.append(str(a) + "x^(" + str(e) + ")")
            elif t == 1:
                a = xrand(5)
                if a <= 1:
                    a = "e"
                s.append("+-"[xrand(2)] + str(a) + "^x")
            elif t == 2:
                a = xrand(6)
                if a < 1:
                    a = 1
                if xrand(2):
                    a = -a
                op = ["sin", "cos", "tan", "sec", "csc", "cot", "log"]
                s.append(str(a) + "*" + choice(op) + "(x)")
        st = ""
        for i in s:
            if st and i[0] not in "+-":
                st += "+"
            st += i
        ans = await self.bot.solve_math(st, xrand(2147483648), 0, 1)
        a = ans[0]
        q = self.eqtrans(a)
        if xrand(2):
            q = "Dₓ " + q
            op = sympy.diff
        else:
            q = "∫ " + q
            op = sympy.integrate
        a = await create_future(op, a, timeout=8)
        return q, a

    # Selects a random math question based on difficulty.
    async def generateMathQuestion(self, mode):
        easy = (
            self.addition,
            self.subtraction,
            self.multiplication,
            self.division,
            self.exponentiation,
            self.square_root,
            self.scientific,
            self.fraction,
            self.recurring,
            self.equation,
        )
        hard = (
            self.multiplication2,
            self.exponentiation2,
            self.square_root2,
            self.equation2,
            self.calculus,
        )
        modes = {"easy": easy, "hard": hard}
        qa = choice(modes[mode])()
        if awaitable(qa):
            return await qa
        return qa

    async def newQuestion(self, channel):
        q, a = await self.generateMathQuestion(self.data[channel.id].mode)
        msg = "```\n" + q + "```"
        self.data[channel.id].answer = a
        await channel.send(msg)

    async def __call__(self):
        bot = self.bot
        for c_id in self.data:
            if self.data[c_id].answer is None:
                self.data[c_id].answer = nan
                channel = await bot.fetch_channel(c_id)
                await self.newQuestion(channel)

    messages = cdict(
        correct=[
            "Great work!",
            "Very nice!",
            "Congrats!",
            "Nice job! Keep going!",
            "That is correct!",
            "Bullseye!",
        ],
        incorrect=[
            "Aw, close, keep trying!",
            "Oops, not quite, try again!",
        ],
    )

    async def _nocommand_(self, message, **void):
        bot = self.bot
        channel = message.channel
        if channel.id in self.data:
            if message.author.id != bot.id:
                msg = message.content.strip("|").strip("`")
                if not msg or msg.casefold() != msg:
                    return
                # Ignore commented messages
                if msg.startswith("#") or msg.startswith("//") or msg.startswith("\\"):
                    return
                try:
                    x = await bot.solve_math(msg, message.author, 0, 1)
                    x = await create_future(sympy.sympify, x[0], timeout=6)
                except:
                    return
                correct = False
                a = self.data[channel.id].answer
                if type(a) is list:
                    if x in a:
                        correct = True
                else:
                    a = await create_future(sympy.sympify, a, timeout=6)
                    d = await create_future(sympy.Add, x, -a, timeout=12)
                    z = await create_future(sympy.simplify, d, timeout=18)
                    correct = z == 0
                if correct:
                    create_task(self.newQuestion(channel))
                    pull = self.messages.correct
                else:
                    pull = self.messages.incorrect
                high = (len(pull) - 1) ** 2
                i = isqrt(random.randint(0, high))
                await channel.send(pull[i])


class Wav2Png(Command):
    _timeout_ = 15
    name = ["Png2Wav", "Png2Mp3"]
    description = "Runs wav2png on the input URL. See https://github.com/thomas-xin/Audio-Image-Converter for more info, or to run it yourself!"
    usage = "<0:search_links>"
    rate_limit = (9, 30)
    typing = True

    async def __call__(self, bot, channel, message, argv, name, **void):
        for a in message.attachments:
            argv = a.url + " " + argv
        if not argv:
            raise ArgumentError("Input string is empty.")
        urls = await bot.follow_url(argv, allow=True, images=False)
        if not urls or not urls[0]:
            raise ArgumentError("Please input a valid URL.")
        url = urls[0]
        fn = url.rsplit("/", 1)[-1].split("?", 1)[0].rsplit(".", 1)[0]
        ts = ts_us()
        ext = "png" if name == "wav2png" else "wav"
        dest = f"cache/&{ts}." + ext
        w2p = "wav2png" if name == "wav2png" else "png2wav"
        args = pillow_simd.get() + [w2p + ".py", url, "../" + dest]
        with discord.context_managers.Typing(channel):
            print(args)
            proc = await asyncio.create_subprocess_exec(*args, cwd=os.getcwd() + "/misc", stdout=subprocess.DEVNULL)
            try:
                await asyncio.wait_for(proc.wait(), timeout=3200)
            except (T0, T1, T2):
                with tracebacksuppressor:
                    proc.kill()
                raise
        await bot.send_with_file(channel, "", dest, filename=fn + "." + ext, reference=message)


class SpectralPulse(Command):
    _timeout_ = 150
    description = "Runs SpectralPulse on the input URL. Operates on a global queue system. See https://github.com/thomas-xin/SpectralPulse for more info, or to run it yourself!"
    usage = "<0:search_links>"
    rate_limit = (12, 60)
    typing = True
    spec_sem = Semaphore(1, 256, rate_limit=1)

    async def __call__(self, bot, channel, message, argv, **void):
        for a in message.attachments:
            argv = a.url + " " + argv
        if not argv:
            raise ArgumentError("Input string is empty.")
        urls = await bot.follow_url(argv, allow=True, images=False)
        if not urls or not urls[0]:
            raise ArgumentError("Please input a valid URL.")
        url = urls[0]
        name = url.rsplit("/", 1)[-1].split("?", 1)[0].rsplit(".", 1)[0]
        n1 = name + ".mp4"
        n2 = name + ".png"
        ts = ts_us()
        dest = f"cache/&{ts}"
        fn1 = dest + ".mp4"
        fn2 = dest + ".png"
        args = pillow_simd.get() + ["main.py", "-dest", "../../" + dest, url]
        with discord.context_managers.Typing(channel):
            if self.spec_sem.is_busy():
                await send_with_react(channel, italics(ini_md(f"SpectralPulse: {sqr_md(url)} enqueued in position {sqr_md(self.spec_sem.passive + 1)}.")), reacts="❎", reference=message)
            async with self.spec_sem:
                print(args)
                proc = await asyncio.create_subprocess_exec(*args, cwd=os.getcwd() + "/misc/spectralpulse", stdout=subprocess.DEVNULL)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3200)
                except (T0, T1, T2):
                    with tracebacksuppressor:
                        proc.kill()
                    raise
                for ext in ("pcm", "riff"):
                    await create_future(os.remove, f"{dest}.{ext}")
        await bot.send_with_file(channel, "", fn1, filename=n1, reference=message)
        await bot.send_with_file(channel, "", fn2, filename=n2, reference=message)


class DeviantArt(Command):
    server_only = True
    min_level = 2
    description = "Subscribes to a DeviantArt Gallery, reposting links to all new posts."
    usage = "(add|remove)? <url> <reversed{?r}>?"
    flags = "raed"
    rate_limit = 4

    async def __call__(self, argv, flags, channel, guild, bot, **void):
        data = bot.data.deviantart
        update = bot.data.deviantart.update
        if not argv:
            assigned = data.get(channel.id, ())
            if not assigned:
                return ini_md(f"No currently subscribed DeviantArt Galleries for {sqr_md(channel)}.")
            if "d" in flags:
                data.pop(channel.id, None)
                return css_md(f"Successfully removed all DeviantArt Gallery subscriptions from {sqr_md(channel)}.")
            return f"Currently subscribed DeviantArt Galleries for {sqr_md(channel)}:{ini_md(iter2str(assigned, key=lambda x: x['user']))}"
        urls = await bot.follow_url(argv, images=False, allow=True)
        if not urls:
            raise ArgumentError("Please input a valid URL.")
        url = urls[0]
        if "deviantart.com" not in url:
            raise ArgumentError("Please input a DeviantArt Gallery URL.")
        # Parse DeviantArt gallery URls
        url = url[url.index("deviantart.com") + 15:]
        spl = url.split("/")
        user = spl[0]
        if spl[1] != "gallery":
            raise ArgumentError("Only Gallery URLs are supported.")
        content = spl[2].split("&", 1)[0]
        folder = no_md(spl[-1].split("&", 1)[0])
        # Gallery may be an ID or "all"
        try:
            content = int(content)
        except (ValueError, TypeError):
            if content in (user, "all"):
                content = user
            else:
                raise TypeError("Invalid Gallery type.")
        if content in self.data.get(channel.id, {}):
            raise KeyError(f"Already subscribed to {user}: {folder}")
        if "d" in flags:
            try:
                data.get(channel.id).pop(content)
            except KeyError:
                raise KeyError(f"Not currently subscribed to {user}: {folder}")
            else:
                if channel.id in data and not data[channel.id]:
                    data.pop(channel.id)
                return css_md(f"Successfully unsubscribed from {sqr_md(user)}: {sqr_md(folder)}.")
        set_dict(data, channel.id, {}).__setitem__(content, {"user": user, "type": "gallery", "reversed": ("r" in flags), "entries": {}})
        update(channel.id)
        out = f"Successfully subscribed to {sqr_md(user)}: {sqr_md(folder)}"
        if "r" in flags:
            out += ", posting in reverse order"
        return css_md(out + ".")


class UpdateDeviantArt(Database):
    name = "deviantart"

    async def processPart(self, found, c_id):
        bot = self.bot
        try:
            channel = await bot.fetch_channel(c_id)
        except LookupError:
            self.data.pop(c_id, None)
            return
        try:
            assigned = self.data.get(c_id)
            if assigned is None:
                return
            embs = deque()
            for content in assigned:
                items = found[content]
                entries = assigned[content]["entries"]
                new = tuple(items)
                orig = tuple(entries)
                # O(n) comparison
                if assigned[content].get("reversed", False):
                    it = reversed(new)
                else:
                    it = new
                for i in it:
                    if i not in entries:
                        entries[i] = True
                        self.update(c_id)
                        home = "https://www.deviantart.com/" + items[i][2]
                        emb = discord.Embed(
                            colour=discord.Colour(1),
                            description="*🔔 New Deviation from " + items[i][2] + " 🔔*\n" + items[i][0],
                        ).set_image(url=items[i][1]).set_author(name=items[i][2], url=home, icon_url=items[i][3])
                        embs.append(emb)
                for i in orig:
                    if i not in items:
                        entries.pop(i)
                        self.update(c_id)
        except:
            print(found)
            print_exc()
        else:
            bot.send_embeds(channel, embs)

    async def __call__(self):
        t = set_dict(self.__dict__, "time", 0)
        # Fetches once every 5 minutes
        if utc() - t < 300:
            return
        self.time = inf
        conts = {i: a[i]["user"] for a in tuple(self.data.values()) for i in a}
        total = {}
        base = "https://www.deviantart.com/_napi/da-user-profile/api/gallery/contents?username="
        attempts, successes = 0, 0
        for content, user in conts.items():
            with tracebacksuppressor:
                # "all" galleries require different URL options
                if type(content) is str:
                    f_id = "&all_folder=true&mode=oldest"
                else:
                    f_id = "&folderid=" + str(content)
                url = base + user + f_id
                # New binary search algorithm to improve search time for entire galleries
                maxitems = 2147483647
                r = 0
                t = utc()
                found = {}
                futs = deque()
                page = 24
                # Begin with quaternary search (powers of 4) to estimate lowest power of 2 greater than or equal to gallery page count
                with suppress(StopIteration):
                    for i in range(2 + int(math.log2(maxitems / page))):
                        curr = 1 << i
                        search = url + f"&offset={curr * page}&limit={page}"
                        futs.append((curr, create_task(Request(search, timeout=20, json=True, aio=True))))
                        if i & 1:
                            for x, fut in futs:
                                resp = await fut
                                if resp.get("results"):
                                    found[x] = resp
                                if not resp.get("hasMore"):
                                    curr = x
                                    raise StopIteration
                        r += 1
                # Once the end has been reached, use binary search to estimate the page count again, being off by at most 8 pages
                check = 1 << max(0, i - 2)
                while check > 4:
                    x = curr - check
                    search = url + f"&offset={x * page}&limit={page}"
                    resp = await Request(search, json=True, aio=True)
                    if resp.get("results"):
                        found[x] = resp
                    r += 1
                    if not resp.get("hasMore"):
                        curr = x
                    check >>= 1
                futs = deque()
                for i in range(curr + 1):
                    if i not in found:
                        search = url + f"&offset={i * page}&limit={page}"
                        futs.append((i, create_task(Request(search, json=True, aio=True))))
                        r += 1
                for x, fut in futs:
                    resp = await fut
                    if resp.get("results"):
                        found[x] = resp
                # Collect all page results into a single list
                results = alist()
                for resp in found.values():
                    results.extend(resp.get("results", ()))
                items = {}
                for res in results:
                    deviation = res["deviation"]
                    media = deviation["media"]
                    prettyName = media["prettyName"]
                    orig = media["baseUri"]
                    extra = ""
                    token = "?token=" + media["token"][0]
                    # Attempt to find largest available format for media
                    for t in reversed(media["types"]):
                        if t["t"].casefold() == "fullview":
                            if "c" in t:
                                extra = "/" + t["c"].replace("<prettyName>", prettyName)
                                break
                    image_url = orig + extra + token
                    items[deviation["deviationId"]] = (deviation["url"], image_url, deviation["author"]["username"], deviation["author"]["usericon"])
                total[content] = items
        # if attempts:
        #     print(successes, "of", attempts, "DeviantArt requests executed successfully.")
        for c_id in tuple(self.data):
            create_task(self.processPart(total, c_id))
        self.time = utc()
