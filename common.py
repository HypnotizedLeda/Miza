import smath
from smath import *

with MultiThreadedImporter(globals()) as importer:
    importer.__import__(
        # "importlib",
        "inspect",
        "tracemalloc",
        "psutil",
        "subprocess",
        "asyncio",
        "discord",
        "json",
        "aiohttp",
        "threading",
        "urllib",
        "zipfile",
        "nacl",
        "shutil",
        "filetype",
    )

PROC = psutil.Process()
quit = lambda *args, **kwargs: PROC.kill()
BOT = [None]

tracemalloc.start()

from zipfile import ZipFile
import urllib.request, urllib.parse
import nacl.secret

utils = discord.utils
requests = requests.Session()
url_parse = urllib.parse.quote_plus
escape_markdown = utils.escape_markdown
escape_mentions = utils.escape_mentions
escape_everyone = lambda s: s.replace("@everyone", "@\xadeveryone").replace("@here", "@\xadhere")
escape_roles = lambda s: escape_everyone(s).replace("<@&", "<@\xad&")

DISCORD_EPOCH = 1420070400000 # 1 Jan 2015
MIZA_EPOCH = 1577797200000 # 1 Jan 2020

time_snowflake = lambda dt, high=None: utils.time_snowflake(dt, high) if type(dt) is not int else getattr(dt, "id", None) or dt

def id2ts(id):
    i = (id >> 22) + (id & 0xFFF)
    try:
        j = i + (id & 0xFFF) / 0x1000
    except OverflowError:
        return (i + DISCORD_EPOCH) // 1000
    return (j + DISCORD_EPOCH) / 1000

def id2td(id):
    i = (id >> 22) + (id & 0xFFF)
    try:
        j = i + (id & 0xFFF) / 0x1000
    except OverflowError:
        return i // 1000
    return j / 1000

def snowflake_time(id):
    i = getattr(id, "id", None)
    if i is None:
        i = id
    if type(i) is int:
        return utc_dft(id2ts(i))
    return i

snowflake_time_2 = lambda id: datetime.datetime.fromtimestamp(id2ts(id))
snowflake_time_3 = utils.snowflake_time

ip2int = lambda ip: int.from_bytes(b"\x00" + bytes(int(i) for i in ip.split(".")), "big")

emptyfut = fut_nop = asyncio.Future()
fut_nop.set_result(None)
newfut = concurrent.futures.Future()
newfut.set_result(None)

def as_fut(obj):
    fut = asyncio.Future()
    eloop.call_soon_threadsafe(fut.set_result, obj)
    return fut


class EmptyContext(contextlib.AbstractContextManager):
    __enter__ = lambda self, *args: self
    __exit__ = lambda *args: None
    __aenter__ = lambda self, *args: as_fut(self)
    __aexit__ = lambda *args: emptyfut

emptyctx = EmptyContext()


# Manages concurrency limits, similar to asyncio.Semaphore, but has a secondary threshold for enqueued tasks.
class Semaphore(contextlib.AbstractContextManager, contextlib.AbstractAsyncContextManager, contextlib.ContextDecorator, collections.abc.Callable):

    __slots__ = ("limit", "buffer", "fut", "active", "passive", "rate_limit", "rate_bin", "last", "trace")

    def __init__(self, limit=256, buffer=32, delay=0.05, rate_limit=None, randomize_ratio=2, last=False, trace=False):
        self.limit = limit
        self.buffer = buffer
        self.active = 0
        self.passive = 0
        self.rate_limit = rate_limit
        self.rate_bin = deque()
        self.fut = concurrent.futures.Future()
        self.fut.set_result(None)
        self.last = last
        self.trace = trace and inspect.stack()[1]

    def __str__(self):
        classname = str(self.__class__).replace("'>", "")
        classname = classname[classname.index("'") + 1:]
        return f"<{classname} object at {hex(id(self)).upper().replace('X', 'x')}>: {self.active}/{self.limit}, {self.passive}/{self.buffer}, {len(self.rate_bin)}/{self.rate_limit}"

    def _update_bin_after(self, t):
        time.sleep(t)
        self._update_bin()

    def _update_bin(self):
        if self.rate_limit:
            try:
                if self.last:
                    if self.rate_bin and time.time() - self.rate_bin[-1] >= self.rate_limit:
                        self.rate_bin.clear()
                else:
                    while self.rate_bin and time.time() - self.rate_bin[0] >= self.rate_limit:
                        self.rate_bin.popleft()
            except IndexError:
                pass
            if len(self.rate_bin) < self.limit:
                try:
                    self.fut.set_result(None)
                except concurrent.futures.InvalidStateError:
                    pass
        return self.rate_bin

    def enter(self):
        if self.trace:
            self.trace = inspect.stack()[2]
        self.active += 1
        if self.rate_limit:
            self._update_bin().append(time.time())
        if self.fut.done() and (self.active >= self.limit or self.rate_limit and len(self.rate_bin) >= self.limit):
            self.fut = concurrent.futures.Future()
        return self

    def check_overflow(self):
        if self.passive >= self.buffer:
            raise SemaphoreOverflowError(f"Semaphore object of limit {self.limit} overloaded by {self.passive}")

    def __enter__(self):
        if self.is_busy():
            self.check_overflow()
            self.passive += 1
            while self.is_busy():
                self.fut.result()
            self.passive -= 1
        return self.enter()

    def __exit__(self, *args):
        self.active -= 1
        if self.rate_bin:
            t = self.rate_bin[0 - self.last] + self.rate_limit - time.time()
            if t > 0:
                create_future_ex(self._update_bin_after, t, priority=True)
            else:
                self._update_bin()
        elif self.active < self.limit:
            try:
                self.fut.set_result(None)
            except concurrent.futures.InvalidStateError:
                pass

    async def __aenter__(self):
        if self.is_busy():
            self.check_overflow()
            self.passive += 1
            while self.is_busy():
                await wrap_future(self.fut)
            self.passive -= 1
        self.enter()
        return self

    def __aexit__(self, *args):
        self.__exit__()
        return emptyfut

    def wait(self):
        while self.is_busy():
            self.fut.result()

    async def __call__(self):
        while self.is_busy():
            await wrap_future(self.fut)
    
    acquire = __call__

    def is_active(self):
        return self.active or self.passive

    def is_busy(self):
        return self.active >= self.limit or self.rate_limit and len(self._update_bin()) >= self.limit

    @property
    def busy(self):
        return self.is_busy()

class SemaphoreOverflowError(RuntimeError):
    __slots__ = ()


# A context manager that sends exception tracebacks to stdout.
class TracebackSuppressor(contextlib.AbstractContextManager, contextlib.AbstractAsyncContextManager, contextlib.ContextDecorator, collections.abc.Callable):

    def __init__(self, *args, **kwargs):
        self.exceptions = args + tuple(kwargs.values())

    def __exit__(self, exc_type, exc_value, exc_tb):
        if exc_type and exc_value:
            for exception in self.exceptions:
                if issubclass(type(exc_value), exception):
                    return True
            try:
                raise exc_value
            except:
                print_exc()
        return True

    def __aexit__(self, *args):
        return as_fut(self.__exit__(*args))

    __call__ = lambda self, *args, **kwargs: self.__class__(*args, **kwargs)

tracebacksuppressor = TracebackSuppressor()


# A context manager that delays the return of a function call.
class Delay(contextlib.AbstractContextManager, contextlib.AbstractAsyncContextManager, contextlib.ContextDecorator, collections.abc.Callable):

    def __init__(self, duration=0):
        self.duration = duration
        self.start = utc()

    def __call__(self):
        return self.exit()

    def __exit__(self, *args):
        remaining = self.duration - utc() + self.start
        if remaining > 0:
            time.sleep(remaining)

    async def __aexit__(self, *args):
        remaining = self.duration - utc() + self.start
        if remaining > 0:
            await asyncio.sleep(remaining)


# A context manager that monitors the amount of time taken for a designated section of code.
class MemoryTimer(contextlib.AbstractContextManager, contextlib.AbstractAsyncContextManager, contextlib.ContextDecorator, collections.abc.Callable):

    timers = cdict()

    @classmethod
    def list(cls):
        return "\n".join(str(name) + ": " + str(duration) for duration, name in sorted(((mean(v), k) for k, v in cls.timers.items()), reverse=True))

    def __init__(self, name=None):
        self.name = name
        self.start = utc()

    def __call__(self):
        return self.exit()

    def __exit__(self, *args):
        taken = utc() - self.start
        try:
            self.timers[self.name].append(taken)
        except KeyError:
            self.timers[self.name] = t = deque(maxlen=8)
            t.append(taken)

    def __aexit__(self, *args):
        self.__exit__()
        return emptyfut


# Repeatedly retries a synchronous operation, with optional break exceptions.
def retry(func, *args, attempts=5, delay=1, exc=(), **kwargs):
    for i in range(attempts):
        t = utc()
        try:
            return func(*args, **kwargs)
        except BaseException as ex:
            if i >= attempts - 1 or ex in exc:
                raise
        remaining = delay - utc() + t
        if remaining > 0:
            time.sleep(delay)

# Repeatedly retries a asynchronous operation, with optional break exceptions.
async def aretry(func, *args, attempts=5, delay=1, exc=(), **kwargs):
    for i in range(attempts):
        t = utc()
        try:
            return await func(*args, **kwargs)
        except BaseException as ex:
            if i >= attempts - 1 or ex in exc:
                raise
        remaining = delay - utc() + t
        if remaining > 0:
            await asyncio.sleep(delay)


# For compatibility with versions of asyncio and concurrent.futures that have the exceptions stored in a different module
T0 = TimeoutError
try:
    T1 = asyncio.exceptions.TimeoutError
except AttributeError:
    try:
        T1 = asyncio.TimeoutError
    except AttributeError:
        T1 = TimeoutError
try:
    T2 = concurrent.futures._base.TimeoutError
except AttributeError:
    try:
        T2 = concurrent.futures.TimeoutError
    except AttributeError:
        T2 = TimeoutError

try:
    ISE = asyncio.exceptions.InvalidStateError
except AttributeError:
    ISE = asyncio.InvalidStateError


class ArgumentError(LookupError):
    __slots__ = ()

class TooManyRequests(PermissionError):
    __slots__ = ()

class CommandCancelledError(RuntimeError):
    __slots__ = ()


python = sys.executable


with open("auth.json") as f:
    AUTH = eval(f.read())

enc_key = None
with tracebacksuppressor:
    enc_key = AUTH["encryption_key"]

if not enc_key:
    enc_key = AUTH["encryption_key"] = as_str(base64.b64encode(randbytes(32)).rstrip(b"="))
    with open("auth.json", "w", encoding="utf-8") as f:
        json.dump(AUTH, f, indent=4)

enc_key += "=="
if (len(enc_key) - 1) & 3 == 0:
    enc_key += "="

enc_box = nacl.secret.SecretBox(base64.b64decode(enc_key)[:32])

encrypt = lambda s: b">~MIZA~>" + enc_box.encrypt(s if type(s) is bytes else str(s).encode("utf-8"))
def decrypt(s):
    if type(s) is not bytes:
        s = str(s).encode("utf-8")
    if s[:8] == b">~MIZA~>":
        return enc_box.decrypt(s[8:])
    raise ValueError("Data header not found.")


def zip2bytes(data):
    if not hasattr(data, "read"):
        data = io.BytesIO(data)
    with ZipFile(data, compression=zipfile.ZIP_DEFLATED, allowZip64=True, strict_timestamps=False) as z:
        b = z.read("DATA")
    return b

def bytes2zip(data):
    b = io.BytesIO()
    with ZipFile(b, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        z.writestr("DATA", data=data)
    b.seek(0)
    return b.read()


# Safer than raw eval, more powerful than json.decode
def eval_json(s):
    if type(s) is memoryview:
        s = bytes(s)
    try:
        return json.loads(s)
    except:
        try:
            return safe_eval(s)
        except:
            pass
        raise

def select_and_loads(s, mode="safe", size=None):
    if not s:
        raise ValueError("Data must not be empty.")
    if size and size < len(s):
        raise OverflowError("Data input size too large.")
    if type(s) is str:
        s = s.encode("utf-8")
    if mode != "unsafe":
        try:
            s = decrypt(s)
        except ValueError:
            pass
        except:
            raise
        else:
            time.sleep(0.1)
    b = io.BytesIO(s)
    if zipfile.is_zipfile(b):
        if len(s) > 1048576:
            print(f"Loading zip file of size {len(s)}...")
        b.seek(0)
        with ZipFile(b, compression=zipfile.ZIP_DEFLATED, allowZip64=True, strict_timestamps=False) as z:
            if size:
                x = z.getinfo("DATA").file_size
                if size < x:
                    raise OverflowError(f"Data input size too large ({x} > {size}).")
            s = z.read("DATA")
    data = None
    with tracebacksuppressor:
        if s[0] == 128:
            data = pickle.loads(s)
    if data is None:
        if mode == "unsafe":
            data = eval(compile(s.strip(b"\0"), "<loader>", "eval", optimize=2, dont_inherit=False))
        else:
            if b"{" in s:
                s = s[s.index(b"{"):s.rindex(b"}") + 1]
            data = json.loads(s)
    return data

def select_and_dumps(data, mode="safe"):
    if mode == "unsafe":
        s = pickle.dumps(data)
        if len(s) > 32768:
            s = bytes2zip(s)
        return s
    try:
        s = json.dumps(data).encode("utf-8")
    except:
        s = None
    if len(s) > 262144:
        return bytes2zip(s)
    return s


class FileHashDict(collections.abc.MutableMapping):

    sem = Semaphore(64, 128, 0.3, 1)

    def __init__(self, *args, path="", **kwargs):
        if not kwargs and len(args) == 1:
            self.data = args[0]
        else:
            self.data = dict(*args, **kwargs)
        self.path = path.rstrip("/")
        self.modified = set()
        self.deleted = set()
        self.iter = None
        if self.path and not os.path.exists(self.path):
            os.mkdir(self.path)
            self.iter = []

    __hash__ = lambda self: lambda self: hash(self.path)
    __str__ = lambda self: self.__class__.__name__ + "(" + str(self.data) + ")"
    __repr__ = lambda self: self.__class__.__name__ + "(" + str(self.full) + ")"
    __call__ = lambda self, k: self.__getitem__(k)
    __len__ = lambda self: len(self.keys())
    __contains__ = lambda self, k: (k in self.data or k in self.keys()) and k not in self.deleted
    __eq__ = lambda self, other: self.data == other
    __ne__ = lambda self, other: self.data != other

    def key_path(self, k):
        return f"{self.path}/{k}"

    @property
    def full(self):
        out = {}
        waits = set()
        for k in self.keys():
            try:
                out[k] = self.data[k]
            except KeyError:
                out[k] = create_future_ex(self.__getitem__, k)
                waits.add(k)
        for k in waits:
            out[k] = out[k].result()
        return out

    def keys(self):
        if self.iter is None or self.modified or self.deleted:
            gen = (try_int(i) for i in os.listdir(self.path) if not i.endswith("\x7f") and i not in self.deleted)
            if self.modified:
                gen = set(gen)
                gen.update(self.modified)
            self.iter = alist(gen)
        return self.iter

    def values(self):
        for k in self.keys():
            with suppress(KeyError):
                yield self[k]

    def items(self):
        for k in self.keys():
            with suppress(KeyError):
                yield (k, self[k])

    def __iter__(self):
        return iter(self.keys())

    def __reversed__(self):
        return reversed(self.keys())

    def __getitem__(self, k):
        if k in self.deleted:
            raise KeyError(k)
        with suppress(KeyError):
            return self.data[k]
        fn = self.key_path(k)
        if not os.path.exists(fn):
            fn += "\x7f\x7f"
            if not os.path.exists(fn):
                raise KeyError(k)
        with self.sem:
            with open(fn, "rb") as f:
                s = f.read()
        fn = fn.rstrip("\x7f")
        data = BaseException
        with tracebacksuppressor:
            data = select_and_loads(s, mode="unsafe")
        if data is BaseException:
            for file in sorted(os.listdir("backup"), reverse=True):
                with tracebacksuppressor:
                    with zipfile.ZipFile("backup/" + file, compression=zipfile.ZIP_DEFLATED, allowZip64=True, strict_timestamps=False) as z:
                        time.sleep(0.03)
                        s = z.read(fn)
                    data = select_and_loads(s, mode="unsafe")
                    self.modified.add(k)
                    print(f"Successfully recovered backup of {fn} from {file}.")
                    break
        if data is BaseException:
            raise BaseException(k)
        self.data[k] = data
        return data

    def __setitem__(self, k, v):
        with suppress(ValueError):
            k = int(k)
        self.deleted.discard(k)
        # try:
        #     if self.data[k] is v:
        #         return
        # except (TypeError, KeyError, ValueError):
        #     pass
        self.data[k] = v
        self.modified.add(k)

    def get(self, k, default=None):
        with suppress(KeyError):
            return self[k]
        return default

    def pop(self, k, *args, force=False):
        fn = self.key_path(k)
        try:
            if force:
                out = self[k]
                self.deleted.add(k)
                return self.data.pop(k, out)
            self.deleted.add(k)
            return self.data.pop(k, None)
        except KeyError:
            if not os.path.exists(fn):
                if args:
                    return args[0]
                raise
            self.deleted.add(k)
            if args:
                return self.data.pop(k, args[0])
            return self.data.pop(k, None)

    __delitem__ = pop

    def popitem(self, k):
        try:
            return self.data.popitem(k)
        except KeyError:
            out = self[k]
        self.pop(k)
        return (k, out)

    def discard(self, k):
        with suppress(KeyError):
            return self.pop(k)

    def setdefault(self, k, v):
        try:
            return self[k]
        except KeyError:
            self[k] = v
        return v

    def update(self, other):
        self.modified.update(other)
        self.update(other)
        return self

    def clear(self):
        if self.iter:
            self.iter.clear()
        self.modified.clear()
        self.data.clear()
        with suppress(FileNotFoundError):
            shutil.rmtree(self.path)
        os.mkdir(self.path)
        return self

    def __update__(self):
        modified = frozenset(self.modified)
        if modified:
            self.iter = None
        self.modified.clear()
        for k in modified:
            fn = self.key_path(k)
            try:
                d = self.data[k]
            except KeyError:
                self.deleted.add(k)
                continue
            s = select_and_dumps(d, mode="unsafe")
            with self.sem:
                safe_save(fn, s)
        deleted = list(self.deleted)
        if deleted:
            self.iter = None
        self.deleted.clear()
        for k in deleted:
            self.data.pop(k, None)
            fn = self.key_path(k)
            with suppress(FileNotFoundError):
                os.remove(fn)
            with suppress(FileNotFoundError):
                os.remove(fn + "\x7f")
            with suppress(FileNotFoundError):
                os.remove(fn + "\x7f\x7f")
        while len(self.data) > 1048576:
            self.data.pop(next(iter(self.data)), None)
        return modified.union(deleted)


def safe_save(fn, s):
    if os.path.exists(fn):
        with open(fn + "\x7f", "wb") as f:
            f.write(s)
        with tracebacksuppressor(FileNotFoundError):
            os.remove(fn + "\x7f\x7f")
    if os.path.exists(fn) and not os.path.exists(fn + "\x7f\x7f"):
        os.rename(fn, fn + "\x7f\x7f")
        os.rename(fn + "\x7f", fn)
    else:
        with open(fn, "wb") as f:
            f.write(s)


# Decodes HTML encoded characters in a string.
def html_decode(s):
    while len(s) > 7:
        try:
            i = s.index("&#")
        except ValueError:
            break
        try:
            if s[i + 2] == "x":
                base = 16
                p = i + 3
            else:
                base = 10
                p = i + 2
            for a in range(p, p + 16):
                c = s[a]
                if c == ";":
                    v = int(s[p:a], base)
                    break
                elif not c.isnumeric() and c not in "abcdefABCDEF":
                    break
            c = chr(v)
            s = s[:i] + c + s[a + 1:]
        except (ValueError, NameError, IndexError):
            s = s[:i + 1] + "\u200b" + s[i + 1:]
            continue
    s = s.replace("\u200b", "").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return s.replace("&quot;", '"').replace("&apos;", "'")


def restructure_buttons(buttons):
    if not buttons:
        return buttons
    if issubclass(type(buttons[0]), collections.abc.Mapping):
        b = alist()
        while buttons:
            b.append(buttons[:5])
            buttons = buttons[5:]
        buttons = b
    used_custom_ids = set()
    for row in buttons:
        for button in row:
            if "type" not in button:
                button["type"] = 2
            if "name" in button:
                button["label"] = button["name"]
            try:
                if type(button["emoji"]) is str:
                    button["emoji"] = cdict(id=None, name=button["emoji"])
                elif not issubclass(type(button["emoji"]), collections.abc.Mapping):
                    emoji = button["emoji"]
                    button["emoji"] = cdict(name=emoji.name, id=emoji.id, animated=getattr(emoji, "animated", False))
            except KeyError:
                pass
            if "url" in button:
                button["style"] = 5
            elif "custom_id" not in button:
                if "id" in button:
                    button["custom_id"] = button["id"]
                else:
                    button["custom_id"] = custom_id = button.get("label")
                    if not custom_id:
                        if button.get("emoji"):
                            button["custom_id"] = min_emoji(button["emoji"])
                        else:
                            button["custom_id"] = 0
            while button["custom_id"] in used_custom_ids:
                if "?" in button["custom_id"]:
                    spl = button["custom_id"].rsplit("?", 1)
                    button["custom_id"] = spl[0] + f"?{int(spl[-1]) + 1}"
                else:
                    button["custom_id"] = button["custom_id"] + "?0"
            used_custom_ids.add(button["custom_id"])
            if "style" not in button:
                button["style"] = 1
            if button.get("emoji"):
                if button["emoji"].get("name") == "▪️":
                    button["disabled"] = True
    return [dict(type=1, components=row) for row in buttons]


def interaction_response(bot, message, content=None, embed=None, components=None, buttons=None):
    if hasattr(embed, "to_dict"):
        embed = embed.to_dict()
    if not getattr(message, "int_id", None):
        message.int_id = message.id
    if not getattr(message, "int_token", None):
        message.int_token = message.slash
    return Request(
        f"https://discord.com/api/v9/interactions/{message.int_id}/{message.int_token}/callback",
        data=json.dumps(dict(
            type=4,
            data=dict(
                flags=64,
                content=content,
                embed=embed,
                components=components or restructure_buttons(buttons),
            ),
        )),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bot {bot.token}",
        },
        bypass=False,
        aio=True,
    )

def interaction_patch(bot, message, content=None, embed=None, components=None, buttons=None):
    if hasattr(embed, "to_dict"):
        embed = embed.to_dict()
    if not getattr(message, "int_id", None):
        message.int_id = message.id
    if not getattr(message, "int_token", None):
        message.int_token = message.slash
    return Request(
        f"https://discord.com/api/v9/interactions/{message.int_id}/{message.int_token}/callback",
        data=json.dumps(dict(
            type=7,
            data=dict(
                flags=64,
                content=content,
                embed=embed,
                components=components or restructure_buttons(buttons),
            ),
        )),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bot {bot.token}",
        },
        bypass=False,
        aio=True,
    )


# Escapes syntax in code highlighting markdown.

ESCAPE_T = {
    "[": "⦍",
    "]": "⦎",
    "@": "＠",
    "`": "",
    ";": ";",
}
__emap = "".maketrans(ESCAPE_T)

ESCAPE_T2 = {
    "@": "＠",
    "`": "",
    "#": "♯",
    ";": ";",
}
__emap2 = "".maketrans(ESCAPE_T2)

# Discord markdown format helper functions
no_md = lambda s: str(s).translate(__emap)
clr_md = lambda s: str(s).translate(__emap2)
sqr_md = lambda s: f"[{no_md(s)}]" if not isinstance(s, discord.abc.GuildChannel) else f"[#{no_md(s)}]"

def italics(s):
    if type(s) is not str:
        s = str(s)
    if "*" not in s:
        s = f"*{s}*"
    return s

def bold(s):
    if type(s) is not str:
        s = str(s)
    if "**" not in s:
        s = f"**{s}**"
    return s

single_md = lambda s: f"`{s}`"
code_md = lambda s: f"```\n{s}```" if s else "``` ```"
py_md = lambda s: f"```py\n{s}```" if s else "``` ```"
ini_md = lambda s: f"```ini\n{s}```" if s else "``` ```"
css_md = lambda s, force=False: (f"```css\n{s}```".replace("'", "\u2019").replace('"', "\u201d") if force else ini_md(s)) if s else "``` ```"
fix_md = lambda s: f"```fix\n{s}```" if s else "``` ```"

# Discord object mention formatting
user_mention = lambda u_id: f"<@{u_id}>"
user_pc_mention = lambda u_id: f"<@!{u_id}>"
channel_mention = lambda c_id: f"<#{c_id}>"
role_mention = lambda r_id: f"<@&{r_id}>"

channel_repr = lambda s: as_str(s) if not isinstance(s, discord.abc.GuildChannel) else str(s)


# Counts the number of lines in a file.
def line_count(fn):
    with open(fn, "r", encoding="utf-8") as f:
        data = f.read()
        return alist((len(data), data.count("\n") + 1))


# Checks if a file is a python code file using its filename extension.
is_code = lambda fn: str(fn).endswith(".py") or str(fn).endswith(".pyw")

def touch(file):
    with open(file, "ab"):
        pass


def get_folder_size(path="."):
    return sum(get_folder_size(f.path) if f.is_dir() else f.stat().st_size for f in os.scandir(path))


# Checks if an object can be used in "await" operations.
awaitable = lambda obj: hasattr(obj, "__await__") or issubclass(type(obj), asyncio.Future) or issubclass(type(obj), asyncio.Task) or inspect.isawaitable(obj)

# Async function that waits for a given time interval if the result of the input coroutine is None.
async def wait_on_none(coro, seconds=0.5):
    resp = await coro
    if resp is None:
        await asyncio.sleep(seconds)
    return resp


# Recursively iterates through an iterable finding coroutines and executing them.
async def recursive_coro(item):
    if not issubclass(type(item), collections.abc.MutableSequence):
        return item
    for i, obj in enumerate(item):
        if awaitable(obj):
            if not issubclass(type(obj), asyncio.Task):
                item[i] = create_task(obj)
        elif issubclass(type(obj), collections.abc.MutableSequence):
            item[i] = create_task(recursive_coro(obj))
    for i, obj in enumerate(item):
        if hasattr(obj, "__await__"):
            with suppress():
                item[i] = await obj
    return item


is_channel = lambda channel: issubclass(type(channel), discord.abc.GuildChannel) or type(channel) is discord.abc.PrivateChannel

def is_nsfw(channel):
    try:
        return channel.is_nsfw()
    except AttributeError:
        return True


REPLY_SEM = cdict()
EDIT_SEM = cdict()
# noreply = discord.AllowedMentions(replied_user=False)

async def send_with_reply(channel, reference, content="", embed=None, tts=None, file=None, files=None, buttons=None, mention=False):
    if not channel:
        channel = reference.channel
    bot = BOT[0]
    if getattr(reference, "slash", None) and not embed:
        sem = emptyctx
        inter = True
        url = f"https://discord.com/api/v9/interactions/{reference.id}/{reference.slash}/callback"
        data = dict(
            type=4,
            data=dict(
                flags=64,
                content=content,
            ),
        )
        if embed:
            data["data"]["embed"] = embed.to_dict()
            data["data"].pop("flags", None)
    else:
        fields = {}
        if embed:
            fields["embed"] = embed
        if tts:
            fields["tts"] = tts
        if not (not reference or getattr(reference, "noref", None) or getattr(bot.messages.get(verify_id(reference)), "deleted", None) or getattr(channel, "simulated", None)): 
            if not getattr(reference, "to_message_reference_dict", None):
                if type(reference) is int:
                    reference = cdict(to_message_reference_dict=eval(f"lambda: dict(message_id={reference})"))
                else:
                    reference.to_message_reference_dict = lambda message: dict(message_id=message.id)
            fields["reference"] = reference
            # fields["allowed_mentions"] = noreply
        if file:
            fields["file"] = file
        if files:
            fields["files"] = files
        if not buttons:
            try:
                return await channel.send(content, **fields)
            except discord.HTTPException as ex:
                if fields.get("reference") and "Unknown message" in str(ex):
                    fields.pop("reference")
                    return await channel.send(content, **fields)
                raise
        components = restructure_buttons(buttons)
        try:
            sem = REPLY_SEM[channel.id]
        except KeyError:
            sem = REPLY_SEM[channel.id] = Semaphore(5.1, buffer=256, delay=0.1, rate_limit=5)
        inter = False
        url = f"https://discord.com/api/v9/channels/{channel.id}/messages"
        if getattr(channel, "dm_channel", None):
            channel = channel.dm_channel
        elif not getattr(channel, "recipient", None) and not channel.permissions_for(channel.guild.me).read_message_history:
            fields = {}
            if embed:
                fields["embed"] = embed
            if tts:
                fields["tts"] = tts
            return await channel.send(content, **fields)
        data = dict(
            content=content,
            allowed_mentions=dict(parse=["users", "roles", "everyone"], replied_user=mention)
        )
        if reference:
            data["message_reference"] = dict(message_id=verify_id(reference))
        if components:
            data["components"] = components
        if embed is not None:
            data["embed"] = embed.to_dict()
        if tts is not None:
            data["tts"] = tts
    body = json.dumps(data)
    exc = RuntimeError
    for i in range(xrand(12, 17)):
        try:
            async with sem:
                resp = await Request(
                    url,
                    method="post",
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bot {bot.token}",
                    },
                    bypass=False,
                    aio=True,
                )
        except Exception as ex:
            exc = ex
            if isinstance(ex, ConnectionError) and int(ex.args[0]) in range(400, 500):
                if not inter:
                    print_exc()
                elif ex.errno == 404:
                    continue
                # print_exc()
                fields = {}
                if embed:
                    fields["embed"] = embed
                if tts:
                    fields["tts"] = tts
                return await channel.send(content, **fields)
            print_exc()
        else:
            if not resp:
                return
            if bot:
                M = bot.ExtendedMessage.new
            else:
                M = discord.Message
            return M(state=bot._state, channel=channel, data=eval_json(resp))
        await asyncio.sleep(i + 1)
    raise exc

# Sends a message to a channel, then adds reactions accordingly.
async def send_with_react(channel, *args, reacts=None, reference=None, mention=False, **kwargs):
    with tracebacksuppressor:
        if reference or "buttons" in kwargs:
            sent = await send_with_reply(channel, reference, *args, mention=mention, **kwargs)
        else:
            sent = await channel.send(*args, **kwargs)
        if reacts:
            for react in reacts:
                await sent.add_reaction(react)
        return sent


def select_voice_channel(user, channel):
    # Attempt to match user's currently connected voice channel
    voice = user.voice
    member = user.guild.me
    if voice is None:
        # Otherwise attempt to find closest voice channel to current text channel
        catg = channel.category
        if catg is not None:
            channels = catg.voice_channels
        else:
            channels = None
        if not channels:
            pos = 0 if channel.category is None else channel.category.position
            # Sort by distance from text channel
            channels = sorted(tuple(channel for channel in channel.guild.voice_channels if channel.permissions_for(member).connect and channel.permissions_for(member).speak and channel.permissions_for(member).use_voice_activation), key=lambda channel: (abs(pos - (channel.position if channel.category is None else channel.category.position)), abs(channel.position)))
        if channels:
            vc = channels[0]
        else:
            raise LookupError("Unable to find voice channel.")
    else:
        vc = voice.channel
    return vc


# Creates and starts a coroutine for typing in a channel.
typing = lambda self: create_task(self.trigger_typing())


# Finds the best URL for a discord object's icon, prioritizing proxy_url for images if applicable.
proxy_url = lambda obj: obj if type(obj) is str else (to_png(obj.avatar_url) if getattr(obj, "avatar_url", None) else (obj.proxy_url if is_image(obj.proxy_url) else obj.url))
# Finds the best URL for a discord object's icon.
best_url = lambda obj: obj if type(obj) is str else (to_png(obj.avatar_url) if getattr(obj, "avatar_url", None) else obj.url)
# Finds the worst URL for a discord object's icon.
worst_url = lambda obj: obj if type(obj) is str else (to_png_ex(obj.avatar_url) if getattr(obj, "avatar_url", None) else obj.url)

def get_author(user, u_id=None):
    url = best_url(user)
    bot = BOT[0]
    if bot and "proxies" in bot.data:
        url2 = bot.data.proxies[0].get(shash(url))
        if url2:
            url = url2
        else:
            bot.data.exec.cproxy(url)
    if u_id:
        name = f"{user} ({user.id})"
    else:
        name = str(user)
    return cdict(name=name, icon_url=url, url=url)

# Finds emojis and user mentions in a string.
find_emojis = lambda s: regexp("<a?:[A-Za-z0-9\\-~_]+:[0-9]+>").findall(s)
find_users = lambda s: regexp("<@!?[0-9]+>").findall(s)


def min_emoji(emoji):
    if not getattr(emoji, "id", None):
        if getattr(emoji, "name", None):
            return emoji.name
        emoji = as_str(emoji)
        if emoji.isnumeric():
            return f"<:_:{emoji}>"
        return emoji
    if emoji.animated:
        return f"<a:_:{emoji.id}>"
    return f"<:_:{emoji.id}>"


def get_last_image(message, embeds=True):
    for a in reversed(message.attachments):
        url = a.url
        if is_image(url) is not None:
            return url
    if embeds:
        for e in reversed(message.embeds):
            if e.video:
                return e.video.url
            if e.image:
                return e.image.url
            if e.thumbnail:
                return e.thumbnail.url
    raise FileNotFoundError("Message has no image.")


def get_message_length(message):
    return len(message.system_content or message.content) + sum(len(e) for e in message.embeds) + sum(len(a.url) for a in message.attachments)

def get_message_words(message):
    return word_count(message.system_content or message.content) + sum(word_count(e.description) if e.description else sum(word_count(f.name) + word_count(f.value) for f in e.fields) if e.fields else 0 for e in message.embeds) + len(message.attachments)

# Returns a string representation of a message object.
def message_repr(message, limit=1024, username=False, link=False):
    c = message.content
    s = getattr(message, "system_content", None)
    if s and len(s) > len(c):
        c = s
    if link:
        c = f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}\n" + c
    if username:
        c = user_mention(message.author.id) + ":\n" + c
    data = lim_str(c, limit)
    if message.attachments:
        data += "\n[" + ", ".join(i.url for i in message.attachments) + "]"
    if message.embeds:
        data += "\n⟨" + ", ".join(str(i.to_dict()) for i in message.embeds) + "⟩"
    if message.reactions:
        data += "\n{" + ", ".join(str(i) for i in message.reactions) + "}"
    with suppress(AttributeError):
        t = message.created_at
        if message.edited_at:
            t = message.edited_at
        data += f"\n`({t})`"
    if not data:
        data = css_md(uni_str("[EMPTY MESSAGE]"), force=True)
    return lim_str(data, limit)


def apply_stickers(message, data):
    if data.get("sticker_items"):
        for s in data["sticker_items"]:
            a = cdict(s)
            a.id = int(a.id)
            if s.get("format_type") == 3:
                a.url = f"https://discord.com/stickers/{a.id}.json"
            else:
                a.url = f"https://media.discordapp.net/stickers/{a.id}.png"
            a.filename = a.name
            a.proxy_url = a.url
            message.attachments.append(a)
    return message


EmptyEmbed = discord.embeds._EmptyEmbed

def as_embed(message, link=False):
    emb = discord.Embed(description="").set_author(**get_author(message.author))
    if not message.content:
        if len(message.attachments) == 1:
            url = message.attachments[0].url
            if is_image(url):
                emb.url = url
                emb.set_image(url=url)
                if link:
                    emb.description = lim_str(f"{emb.description}\n\n[View Message](https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id})", 4096)
                    emb.timestamp = message.edited_at or message.created_at
                return emb
        elif not message.attachments and len(message.embeds) == 1:
            emb2 = message.embeds[0]
            if emb2.description != EmptyEmbed and emb2.description:
                emb.description = emb2.description
            if emb2.title:
                emb.title = emb2.title
            if emb2.url:
                emb.url = emb2.url
            if emb2.image:
                emb.set_image(url=emb2.image.url)
            if emb2.thumbnail:
                emb.set_thumbnail(url=emb2.thumbnail.url)
            for f in emb2.fields:
                if f:
                    emb.add_field(name=f.name, value=f.value, inline=getattr(f, "inline", True))
            if link:
                emb.description = lim_str(f"{emb.description}\n\n[View Message](https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id})", 4096)
                emb.timestamp = message.edited_at or message.created_at
            return emb
    else:
        urls = find_urls(message.content)
        if urls:
            with tracebacksuppressor:
                url = urls[0]
                resp = requests.get(url, headers=Request.header(), timeout=8)
                if BOT[0]:
                    BOT[0].activity += 1
                headers = fcdict(resp.headers)
                if headers.get("Content-Type").split("/", 1)[0] == "image":
                    emb.url = url
                    emb.set_image(url=url)
                    if url != message.content:
                        emb.description = message.content
                    if link:
                        emb.description = lim_str(f"{emb.description}\n\n[View Message](https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id})", 4096)
                        emb.timestamp = message.edited_at or message.created_at
                    return emb
    emb.description = message.content
    if len(message.embeds) > 1 or message.content:
        urls = chain(("(" + e.url + ")" for e in message.embeds[1:] if e.url), ("[" + best_url(a) + "]" for a in message.attachments))
        items = list(urls)
    else:
        items = None
    if items:
        if emb.description in items:
            emb.description = lim_str("\n".join(items), 4096)
        elif emb.description or items:
            emb.description = lim_str(emb.description + "\n" + "\n".join(items), 4096)
    image = None
    for a in message.attachments:
        url = a.url
        if is_image(url) is not None:
            image = url
    if not image and message.embeds:
        for e in message.embeds:
            if e.image:
                image = e.image.url
            if e.thumbnail:
                image = e.thumbnail.url
    if image:
        emb.url = image
        emb.set_image(url=image)
    for e in message.embeds:
        if len(emb.fields) >= 25:
            break
        if not emb.description or emb.description == EmptyEmbed:
            title = e.title or ""
            if title:
                emb.title = title
            emb.url = e.url or ""
            description = e.description or e.url or ""
            if description:
                emb.description = description
        else:
            if e.title or e.description:
                emb.add_field(name=e.title or e.url or "\u200b", value=lim_str(e.description, 1024) or e.url or "\u200b", inline=False)
        for f in e.fields:
            if len(emb.fields) >= 25:
                break
            if f:
                emb.add_field(name=f.name, value=f.value, inline=getattr(f, "inline", True))
        if len(emb) >= 6000:
            while len(emb) > 6000:
                emb.remove_field(-1)
            break
    if not emb.description:
        urls = chain(("(" + e.url + ")" for e in message.embeds if e.url), ("[" + best_url(a) + "]" for a in message.attachments))
        emb.description = lim_str("\n".join(urls), 4096)
    if link:
        emb.description = lim_str(f"{emb.description}\n\n[View Message](https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id})", 4096)
        emb.timestamp = message.edited_at or message.created_at
    return emb

exc_repr = lambda ex: lim_str(py_md(f"Error: {repr(ex).replace('`', '')}"), 2000)

# Returns a string representation of an activity object.
def activity_repr(activity):
    if hasattr(activity, "type") and activity.type != discord.ActivityType.custom:
        t = activity.type.name
        if t == "listening":
            t += " to"
        return f"{t.capitalize()} {activity.name}"
    return str(activity)


# Alphanumeric string regular expression.
is_alphanumeric = lambda string: string.replace(" ", "").isalnum()
to_alphanumeric = lambda string: single_space(regexp("[^a-z 0-9]+", re.I).sub(" ", unicode_prune(string)))
is_numeric = lambda string: regexp("[0-9]").search(string) and not regexp("[a-z]", re.I).search(string)


# Strips code box from the start and end of a message.
def strip_code_box(s):
    if s.startswith("```") and s.endswith("```"):
        s = s[s.index("\n") + 1:-3]
    return s


# A string lookup operation with an iterable, multiple attempts, and sorts by priority.
async def str_lookup(it, query, ikey=lambda x: [str(x)], qkey=lambda x: [str(x)], loose=True, fuzzy=0):
    queries = qkey(query)
    qlist = [q for q in queries if q]
    if not qlist:
        qlist = list(queries)
    cache = [[[nan, None], [nan, None]] for _ in qlist]
    for x, i in enumerate(shuffle(it), 1):
        for c in ikey(i):
            if not c and i:
                continue
            if fuzzy:
                for a, b in enumerate(qkey(c)):
                    match = fuzzy_substring(qlist[a], b)
                    if match >= 1:
                        return i
                    elif match >= fuzzy and not match <= cache[a][0][0]:
                        cache[a][0] = [match, i]
            else:
                for a, b in enumerate(qkey(c)):
                    if b == qlist[a]:
                        return i
                    elif b.startswith(qlist[a]):
                        if not len(b) >= cache[a][0][0]:
                            cache[a][0] = [len(b), i]
                    elif loose and qlist[a] in b:
                        if not len(b) >= cache[a][1][0]:
                            cache[a][1] = [len(b), i]
        if not x & 2047:
            await asyncio.sleep(0.1)
    for c in cache:
        if c[0][0] < inf:
            return c[0][1]
    if loose and not fuzzy:
        for c in cache:
            if c[1][0] < inf:
                return c[1][1]
    raise LookupError(f"No results for {query}.")


# Generates a random colour across the spectrum, in intervals of 128.
rand_colour = lambda: colour2raw(hue2colour(xrand(12) * 128))


base_colours = cdict(
    black=(0,) * 3,
    white=(255,) * 3,
    grey=(127,) * 3,
    gray=(127,) * 3,
    dark_grey=(64,) * 3,
    dark_gray=(64,) * 3,
    light_grey=(191,) * 3,
    light_gray=(191,) * 3,
    silver=(191,) * 3,
)
primary_secondary_colours = cdict(
    red=(255, 0, 0),
    green=(0, 255, 0),
    blue=(0, 0, 255),
    yellow=(255, 255, 0),
    cyan=(0, 255, 255),
    aqua=(0, 255, 255),
    magenta=(255, 0, 255),
    fuchsia=(255, 0, 255),
)
tertiary_colours = cdict(
    orange=(255, 127, 0),
    chartreuse=(127, 255, 0),
    lime=(127, 255, 0),
    lime_green=(127, 255, 0),
    spring_green=(0, 255, 127),
    azure=(0, 127, 255),
    violet=(127, 0, 255),
    rose=(255, 0, 127),
    dark_red=(127, 0, 0),
    maroon=(127, 0, 0),
)
colour_shades = cdict(
    dark_green=(0, 127, 0),
    dark_blue=(0, 0, 127),
    navy_blue=(0, 0, 127),
    dark_yellow=(127, 127, 0),
    dark_cyan=(0, 127, 127),
    teal=(0, 127, 127),
    dark_magenta=(127, 0, 127),
    dark_orange=(127, 64, 0),
    brown=(127, 64, 0),
    dark_chartreuse=(64, 127, 0),
    dark_spring_green=(0, 127, 64),
    dark_azure=(0, 64, 127),
    dark_violet=(64, 0, 127),
    dark_rose=(127, 0, 64),
    light_red=(255, 127, 127),
    peach=(255, 127, 127),
    light_green=(127, 255, 127),
    light_blue=(127, 127, 255),
    light_yellow=(255, 255, 127),
    light_cyan=(127, 255, 255),
    turquoise=(127, 255, 255),
    light_magenta=(255, 127, 255),
    light_orange=(255, 191, 127),
    light_chartreuse=(191, 255, 127),
    light_spring_green=(127, 255, 191),
    light_azure=(127, 191, 255),
    sky_blue=(127, 191, 255),
    light_violet=(191, 127, 255),
    purple=(191, 127, 255),
    light_rose=(255, 127, 191),
    pink=(255, 127, 191),
)
colour_types = (
    colour_shades,
    base_colours,
    primary_secondary_colours,
    tertiary_colours,
)

def get_colour_list():
    global colour_names
    with tracebacksuppressor:
        colour_names = cdict()
        resp = Request("https://en.wikipedia.org/wiki/List_of_colors_(compact)", decode=True, timeout=None)
        resp = resp.split('<span class="mw-headline" id="List_of_colors">List of colors</span>', 1)[-1].split("</h3>", 1)[-1].split("<h2>", 1)[0]
        n = len("background-color:rgb")
        while resp:
            try:
                i = resp.index("background-color:rgb")
            except ValueError:
                break
            colour, resp = resp[i + n:].split(";", 1)
            colour = literal_eval(colour)
            resp = resp.split("<a ", 1)[-1].split(">", 1)[-1]
            name, resp = resp.split("<", 1)
            name = full_prune(name).strip().replace(" ", "_")
            if "(" in name and ")" in name:
                name = (name.split("(", 1)[0] + name.rsplit(")", 1)[-1]).strip("_")
                if name in colour_names:
                    continue
            colour_names[name] = colour
        for colour_group in colour_types:
            if colour_group:
                if not colour_names:
                    colour_names = cdict(colour_group)
                else:
                    colour_names.update(colour_group)
        print(f"Successfully loaded {len(colour_names)} colour names.")

def parse_colour(s, default=None):
    if s.startswith("0x"):
        s = s[2:].rstrip()
    else:
        s = single_space(s.replace("#", "").replace(",", " ")).strip()
    # Try to parse as colour tuple first
    if not s:
        if default is None:
            raise ArgumentError("Missing required colour argument.")
        return default
    try:
        return colour_names[full_prune(s).replace(" ", "_")]
    except KeyError:
        pass
    if " " in s:
        channels = [min(255, max(0, int(round(float(i.strip()))))) for i in s.split(" ")[:5] if i]
        if len(channels) not in (3, 4):
            raise ArgumentError("Please input 3 or 4 channels for colour input.")
    else:
        # Try to parse as hex colour value
        try:
            raw = int(s, 16)
            if len(s) <= 6:
                channels = [raw >> 16 & 255, raw >> 8 & 255, raw & 255]
            elif len(s) <= 8:
                channels = [raw >> 16 & 255, raw >> 8 & 255, raw & 255, raw >> 24 & 255]
            else:
                raise ValueError
        except ValueError:
            raise ArgumentError("Please input a valid colour identifier.")
    return channels


# Gets the string representation of a url object with the maximum allowed image size for discord, replacing webp with png format when possible.
def to_png(url):
    if type(url) is not str:
        url = str(url)
    if url.endswith("?size=1024"):
        url = url[:-10] + "?size=4096"
    if "/embed/" not in url[:48]:
        url = url.replace("/cdn.discordapp.com/", "/media.discordapp.net/")
    return url.replace(".webp", ".png")

def to_png_ex(url):
    if type(url) is not str:
        url = str(url)
    if url.endswith("?size=1024"):
        url = url[:-10] + "?size=256"
    if "/embed/" not in url[:48]:
        url = url.replace("/cdn.discordapp.com/", "/media.discordapp.net/")
    return url.replace(".webp", ".png")


# A translator to stip all characters from mentions.
__imap = {
    "#": "",
    "<": "",
    ">": "",
    "@": "",
    "!": "",
    "&": "",
}
__itrans = "".maketrans(__imap)

def verify_id(obj):
    if type(obj) is int:
        return obj
    if type(obj) is str:
        with suppress(ValueError):
            return int(obj.translate(__itrans))
        return obj
    with suppress(AttributeError):
        return obj.recipient.id
    with suppress(AttributeError):
        return obj.id
    return int(obj)


# Strips <> characters from URLs.
def strip_acc(url):
    if url.startswith("<") and url[-1] == ">":
        s = url[1:-1]
        if is_url(s):
            return s
    return url

__smap = {"|": "", "*": ""}
__strans = "".maketrans(__smap)
verify_search = lambda f: strip_acc(single_space(f.strip().translate(__strans)))
# This reminds me of Perl - Smudge
find_urls = lambda url: url and regexp("(?:http|hxxp|ftp|fxp)s?:\\/\\/[^\\s`|\"'\\])>]+").findall(url)
is_url = lambda url: url and regexp("^(?:http|hxxp|ftp|fxp)s?:\\/\\/[^\\s`|\"'\\])>]+$").fullmatch(url)
is_discord_url = lambda url: url and regexp("^https?:\\/\\/(?:[A-Za-z]{3,8}\\.)?discord(?:app)?\\.(?:com|net)\\/").findall(url) + regexp("https:\\/\\/images-ext-[0-9]+\\.discordapp\\.net\\/external\\/").findall(url)
is_tenor_url = lambda url: url and regexp("^https?:\\/\\/tenor.com(?:\\/view)?/[a-zA-Z0-9\\-_]+-[0-9]+").findall(url)
is_imgur_url = lambda url: url and regexp("^https?:\\/\\/(?:[A-Za-z]\\.)?imgur.com/[a-zA-Z0-9\\-_]+").findall(url)
is_giphy_url = lambda url: url and regexp("^https?:\\/\\/giphy.com/gifs/[a-zA-Z0-9\\-_]+").findall(url)
is_youtube_url = lambda url: url and regexp("^https?:\\/\\/(?:www\\.)?youtu(?:\\.be|be\\.com)\\/[^\\s<>`|\"']+").findall(url)
is_youtube_stream = lambda url: url and regexp("^https?:\\/\\/r[0-9]+---.{2}-\\w+-\\w{4,}\\.googlevideo\\.com").findall(url)
is_deviantart_url = lambda url: url and regexp("^https?:\\/\\/(?:www\\.)?deviantart\\.com\\/[^\\s<>`|\"']+").findall(url)

def expired(stream):
    if is_youtube_url(stream):
        return True
    if stream.startswith("https://www.yt-download.org/download/"):
        if int(stream.split("/download/", 1)[1].split("/", 4)[3]) < utc() + 60:
            return True
    elif is_youtube_stream(stream):
        if int(stream.replace("/", "=").split("expire=", 1)[-1].split("=", 1)[0].split("&", 1)[0]) < utc() + 60:
            return True

def is_discord_message_link(url):
    check = url[:64]
    return "channels/" in check and "discord" in check

verify_url = lambda url: url if is_url(url) else url_parse(url)


# Checks if a URL contains a valid image extension, and removes it if possible.
IMAGE_FORMS = {
    ".gif": True,
    ".png": True,
    ".bmp": False,
    ".jpg": True,
    ".jpeg": True,
    ".tiff": False,
    ".webp": True,
}
def is_image(url):
    if url:
        url = url.split("?", 1)[0]
        if "." in url:
            url = url[url.rindex("."):]
            url = url.casefold()
            return IMAGE_FORMS.get(url)

VIDEO_FORMS = {
    ".webm": True,
    ".mkv": True,
    ".f4v": False,
    ".flv": True,
    ".ogv": True,
    ".ogg": False,
    ".gif": False,
    ".gifv": True,
    ".avi": True,
    ".mov": True,
    ".qt": True,
    ".wmv": True,
    ".mp4": True,
    ".m4v": True,
    ".mpg": True,
    ".mpeg": True,
    ".mpv": True,
}
def is_video(url):
    if "." in url:
        url = url[url.rindex("."):]
        url = url.casefold()
        return VIDEO_FORMS.get(url)


MIMES = cdict(
    bin="application/octet-stream",
    css="text/css",
    json="application/json",
    js="application/javascript",
    txt="text/plain",
    html="text/html",
    ico="image/x-icon",
    png="image/png",
    jpg="image/jpeg",
    gif="image/gif",
    webp="image/webp",
    mp3="audio/mpeg",
    ogg="audio/ogg",
    opus="audio/opus",
    flac="audio/flac",
    wav="audio/x-wav",
    mp4="video/mp4",
)

def load_mimes():
    with open("misc/mimes.txt") as f:
        mimedata = f.read().splitlines()
        globals()["mimesplitter"] = {}
        for line in mimedata:
            dat, ext, mime = line.split("\t")
            data = hex2bytes(dat)
            try:
                mimesplitter[len(data)][data] = (ext, mime)
            except KeyError:
                mimesplitter[len(data)] = {}
                mimesplitter[len(data)][data] = (ext, mime)

def simple_mimes(b, mime=True):
    for k, v in reversed(mimesplitter.items()):
        out = v.get(b[:k])
        if out:
            return out[mime]
    try:
        s = b.decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream" if mime else "bin"
    return "text/plain" if mime else "txt"


def from_file(path, mime=True):
    path = filetype.get_bytes(path)
    if mime:
        out = filetype.guess_mime(path)
    else:
        out = filetype.guess_extension(path)
    if out and out.split("/", 1)[-1] == "zip" and type(path) is str and path.endswith(".jar"):
        return "application/java-archive"
    if not out:
        out = simple_mimes(path, mime)
    return out

magic = cdict(
    from_file=from_file,
    from_buffer=from_file,
    Magic=lambda mime, *args, **kwargs: cdict(
        from_file=lambda b: from_file(b, mime),
        from_buffer=lambda b: from_file(b, mime),
    ),
)

def get_mime(path):
    if os.path.getsize(path) < 1048576:
        try:
            mime = magic.from_file(path, mime=True)
        except:
            print_exc()
            mime = "cannot open `"
    else:
        mime = "cannot open `"
    if mime.startswith("cannot open `"):
        with open(path, "rb") as f:
            b = f.read(65536)
        mime = magic.from_buffer(b, mime=True)
    if mime == "text/plain":
        mime2 = MIMES.get(path.rsplit("/", 1)[-1].rsplit(".", 1)[-1], "")
        if mime2.startswith("text/"):
            return mime2
    elif mime.split("/", 1)[-1] == "zip" and path.endswith(".jar"):
        return "application/java-archive"
    return mime


status_text = {
    discord.Status.online: "Online",
    discord.Status.idle: "Idle",
    discord.Status.dnd: "DND",
    discord.Status.invisible: "Invisible",
    discord.Status.offline: "Offline",
}
status_icon = {
    discord.Status.online: "🟢",
    discord.Status.idle: "🟡",
    discord.Status.dnd: "🔴",
    discord.Status.invisible: "⚫",
    discord.Status.offline: "⚫",
}
status_order = tuple(status_text)


# GC = cdict()

# def var_count():
#     count = len(gc.get_objects())
#     for k, v in deque(GC.items()):
#         with suppress(psutil.NoSuchProcess):
#             if not psutil.Process(k).is_running():
#                 GC.pop(k, None)
#             else:
#                 count += v
#     return count


# Subprocess pool for resource-consuming operations.
PROC_COUNT = cdict()
PROCS = cdict()
PROC_RESP = {}

# Gets amount of processes running in pool.
sub_count = lambda: sum(sum(1 for p in v if p.is_running()) for v in PROCS.values())

def force_kill(proc):
    with tracebacksuppressor(psutil.NoSuchProcess):
        for child in proc.children(recursive=True):
            with suppress():
                child.kill()
                print(child, "killed.")
        print(proc, "killed.")
        return proc.kill()

def proc_communicate(k, i):
    while True:
        with tracebacksuppressor:
            try:
                proc = PROCS[k][i]
            except LookupError:
                break
            while not proc.is_running():
                time.sleep(0.8)
            s = as_str(proc.stdout.readline()).rstrip()
            if s:
                # print(s)
                if s[0] == "~":
                    c = as_str(eval(s[1:]))
                    create_future_ex(exec_tb, c, globals())
                else:
                    print(s)
        time.sleep(0.01)

proc_args = cdict(
    math=[python, "misc/math.py"],
    image=[python, "misc/image.py"],
)

class Pillow_SIMD:
    args = None
    __bool__ = lambda self: bool(self.args)
    get = lambda self: self.args or [python]

    # def check(self):
    #     for v in range(8, 4, -1):
    #         print(f"Attempting to find/install pillow-simd for Python 3.{v}...")
    #         args = ["py", f"-3.{v}", "misc/install_pillow_simd.py"]
    #         print(args)
    #         resp = subprocess.run(args, stdout=subprocess.PIPE)
    #         out = as_str(resp.stdout).strip()
    #         if not out.startswith(f"Python 3.{v} not found!"):
    #             if out:
    #                 print(out)
    #             print(f"pillow-simd versioning successful for Python 3.{v}")
    #             self.args = ["py", f"-3.{v}"]
    #             return self.args
    #     return [python]

    check = lambda self: [sys.executable]

pillow_simd = Pillow_SIMD()

def proc_start():
    PROC_COUNT.math = 3
    PROC_COUNT.image = 7
    for k, v in PROC_COUNT.items():
        if k == "image":
            proc_args.image = pillow_simd.check() + ["misc/image.py"]
        PROCS[k] = [psutil.Popen(
            proc_args[k],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        ) for _ in loop(v)]
        PROC_COUNT[k] = 0
        for i, proc in enumerate(PROCS[k]):
            proc.sem = Semaphore(1, inf)
            create_thread(proc_communicate, k, i)

def get_idle_proc(ptype):
    p = [i for i in PROCS[ptype] if not i.sem.is_busy()]
    if not p:
        proc = PROCS[ptype][PROC_COUNT[ptype]]
        PROC_COUNT[ptype] = (PROC_COUNT[ptype] + 1) % len(PROCS[ptype])
    else:
        proc = p[0]
    return proc

def sub_submit(ptype, command, _timeout=12):
    if BOT[0]:
        BOT[0].activity += 1
    ts = ts_us()
    proc = get_idle_proc(ptype)
    while ts in PROC_RESP:
        ts += 1
    PROC_RESP[ts] = concurrent.futures.Future()
    command = "[" + ",".join(map(repr, command[:2])) + "," + ",".join(map(str, command[2:])) + "]"
    s = f"~{ts}~{repr(command.encode('utf-8'))}\n".encode("utf-8")
    with proc.sem:
        if not proc.is_running():
            proc = get_idle_proc(ptype)
        try:
            # print(s)
            proc.stdin.write(s)
            proc.stdin.flush()
            resp = PROC_RESP[ts].result(timeout=_timeout)
        except (BrokenPipeError, OSError, concurrent.futures.TimeoutError):
            # print(proc, s)
            print_exc()
            proc.kill()
            proc2 = psutil.Popen(
                proc.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
            proc2.sem = proc.sem
            PROCS[ptype][PROCS[ptype].index(proc)] = proc2
            raise
    PROC_RESP.pop(ts, None)
    return resp

def sub_kill(start=True):
    for v in PROCS.values():
        for p in v:
            create_future_ex(force_kill, p, priority=True)
    PROCS.clear()
    if start:
        return proc_start()


# Sends an operation to the math subprocess pool.
def process_math(expr, prec=64, rat=False, timeout=12, variables=None):
    return create_future(sub_submit, "math", (expr, prec, rat, variables), _timeout=timeout)

# Sends an operation to the image subprocess pool.
def process_image(image, operation, args, timeout=24):
    if type(args) is tuple:
        args = list(args)
    for i, a in enumerate(args):
        if type(a) is mpf:
            args[i] = float(a)
        elif type(a) in (list, deque, np.ndarray, dict):
            args[i] = "pickle.loads(" + repr(pickle.dumps(a)) + ")"

    def as_arg(arg):
        if isinstance(arg, str) and arg.startswith("pickle.loads("):
            return arg
        return repr(arg)

    command = "[" + ",".join(map(as_arg, args)) + "]"
    return create_future(sub_submit, "image", (image, operation, command), _timeout=timeout)


def evalex(exc):
    try:
        ex = eval(exc)
    except (SyntaxError, NameError):
        exc = as_str(exc)
        s = exc[exc.index("(") + 1:exc.index(")")]
        with suppress(TypeError, SyntaxError, ValueError):
            s = ast.literal_eval(s)
        ex = RuntimeError(s)
    return ex

# Evaluates an an expression, raising it if it is an exception.
def evalEX(exc):
    try:
        ex = evalex(exc)
    except:
        print(exc)
        raise
    if issubclass(type(ex), BaseException):
        raise ex
    return ex


# Main event loop for all asyncio operations.
eloop = asyncio.get_event_loop()
__setloop__ = lambda: asyncio.set_event_loop(eloop)


ThreadPoolExecutor = concurrent.futures.ThreadPoolExecutor

# Thread pool manager for multithreaded operations.
class MultiThreadPool(collections.abc.Sized, concurrent.futures.Executor):

    def __init__(self, pool_count=1, thread_count=8, initializer=None):
        self.pools = alist()
        self.pool_count = max(1, pool_count)
        self.thread_count = max(1, thread_count)
        self.initializer = initializer
        self.position = -1
        self.update()

    __len__ = lambda self: sum(len(pool._threads) for pool in self.pools)

    # Adjusts pool count if necessary
    def _update(self):
        if self.pool_count != len(self.pools):
            self.pool_count = max(1, self.pool_count)
            self.thread_count = max(1, self.thread_count)
            while self.pool_count > len(self.pools):
                self.pools.append(ThreadPoolExecutor(max_workers=self.thread_count, initializer=self.initializer))
            while self.pool_count < len(self.pools):
                func = self.pools.popright().shutdown
                self.pools[-1].submit(func, wait=True)

    def update(self):
        if not self.pools:
            self._update()
        self.position = (self.position + 1) % len(self.pools)
        self.pools.next().submit(self._update)

    def map(self, func, *args, **kwargs):
        self.update()
        return self.pools[self.position].map(func, *args, **kwargs)

    def submit(self, func, *args, **kwargs):
        self.update()
        return self.pools[self.position].submit(func, *args, **kwargs)

    shutdown = lambda self, wait=True: [exc.shutdown(wait) for exc in self.pools].append(self.pools.clear())

pthreads = MultiThreadPool(pool_count=2, thread_count=48, initializer=__setloop__)
athreads = MultiThreadPool(pool_count=2, thread_count=64, initializer=__setloop__)

def get_event_loop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        return eloop

# Creates an asyncio Future that waits on a multithreaded one.
def wrap_future(fut, loop=None, shield=False, thread_safe=True):
    if loop is None:
        loop = get_event_loop()
    wrapper = None
    if not thread_safe:
        try:
            wrapper = asyncio.wrap_future(fut, loop=loop)
        except (AttributeError, TypeError):
            pass
    if wrapper is None:
        wrapper = loop.create_future()

        def set_suppress(res, is_exception=False):
            try:
                if is_exception:
                    wrapper.set_exception(res)
                else:
                    wrapper.set_result(res)
            except (RuntimeError, asyncio.InvalidStateError):
                pass

        def on_done(*void):
            try:
                res = fut.result()
            except Exception as ex:
                loop.call_soon_threadsafe(set_suppress, ex, True)
            else:
                loop.call_soon_threadsafe(set_suppress, res)

        fut.add_done_callback(on_done)
    if shield:
        wrapper = asyncio.shield(wrapper)
    return wrapper

def shutdown_thread_after(thread, fut):
    fut.result()
    return thread.shutdown(wait=True)

def create_thread(func, *args, wait=False, **kwargs):
    thread = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = thread.submit(func, *args, **kwargs)
    if wait:
        create_future_ex(shutdown_thread_after, thread, fut, priority=True)
    return thread

# Runs a function call in a parallel thread, returning a future object waiting on the output.
def create_future_ex(func, *args, timeout=None, priority=False, **kwargs):
    try:
        kwargs["timeout"] = kwargs.pop("_timeout_")
    except KeyError:
        pass
    fut = (athreads, pthreads)[priority].submit(func, *args, **kwargs)
    if timeout is not None:
        fut = (athreads, pthreads)[priority].submit(fut.result, timeout=timeout)
    return fut

# Forces the operation to be a coroutine regardless of whether it is or not. Regular functions are executed in the thread pool.
async def _create_future(obj, *args, loop, timeout, priority, **kwargs):
    while asyncio.iscoroutinefunction(obj):
        obj = obj(*args, **kwargs)
    if callable(obj):
        if asyncio.iscoroutinefunction(obj.__call__) or not is_main_thread():
            obj = obj.__call__(*args, **kwargs)
        else:
            obj = await wrap_future(create_future_ex(obj, *args, timeout=timeout, priority=priority, **kwargs), loop=loop)
    while awaitable(obj):
        if timeout is not None:
            obj = await asyncio.wait_for(obj, timeout=timeout)
        else:
            obj = await obj
    return obj

# High level future asyncio creation function that takes both sync and async functions, as well as coroutines directly.
def create_future(obj, *args, loop=None, timeout=None, priority=False, **kwargs):
    if loop is None:
        loop = get_event_loop()
    fut = _create_future(obj, *args, loop=loop, timeout=timeout, priority=priority, **kwargs)
    if not isinstance(fut, asyncio.Task):
        fut = create_task(fut, loop=loop)
    return fut

# Creates an asyncio Task object from an awaitable object.
def create_task(fut, *args, loop=None, **kwargs):
    if loop is None:
        loop = get_event_loop()
    return asyncio.ensure_future(fut, *args, loop=loop, **kwargs)

async def _await_fut(fut, ret):
    out = await fut
    ret.set_result(out)
    return ret

# Blocking call that waits for a single asyncio future to complete, do *not* call from main asyncio loop
def await_fut(fut, timeout=None):
    if is_main_thread():
        if not isinstance(fut, asyncio.Task):
            fut = create_task(fut, loop=loop)
        raise RuntimeError("This function must not be called from the main thread's asyncio loop.")
    try:
        ret = asyncio.run_coroutine_threadsafe(fut, loop=get_event_loop())
    except:
        ret = concurrent.futures.Future()
        create_task(_await_fut(fut, ret))
    return ret.result(timeout=timeout)

is_main_thread = lambda: threading.current_thread() is threading.main_thread()

# A dummy coroutine that returns None.
async_nop = lambda *args, **kwargs: emptyfut

async def delayed_coro(fut, duration=None):
    async with Delay(duration):
        return await fut

async def traceback_coro(fut, *args):
    with tracebacksuppressor(*args):
        return await fut

def trace(fut, *args):
    return create_task(traceback_coro(fut, *args))

# A function that takes a coroutine, and calls a second function if it takes longer than the specified delay.
async def delayed_callback(fut, delay, func, *args, exc=False, **kwargs):
    await asyncio.sleep(delay)
    try:
        return fut.result()
    except ISE:
        res = func(*args, **kwargs)
        if awaitable(res):
            await res
        try:
            return await fut
        except:
            if exc:
                raise
    except:
        if exc:
            raise


def exec_tb(s, *args, **kwargs):
    with tracebacksuppressor:
        exec(s, *args, **kwargs)


def find_file(path, cwd="cache", ind="\x7f"):
    # if no file name is inputted, return no content
    if not path:
        raise EOFError
    # do not include "." in the path name
    path = path.rsplit(".", 1)[0]
    fn = f"{ind}{path}"
    for file in reversed(os.listdir(cwd)):
        # file cache is stored as "{timestamp}~{name}", search for file via timestamp
        if file[-1] != ind and file.rsplit(".", 1)[0].split("~", 1)[0] == fn:
            return os.getcwd() + "/" + cwd + "/" + file
    raise FileNotFoundError(path)


class open2(io.IOBase):

    __slots__ = ("fp", "fn", "mode", "filename")

    def __init__(self, fn, mode="rb", filename=None):
        self.fp = None
        self.fn = fn
        self.mode = mode
        self.filename = filename or getattr(fn, "name", None) or fn

    def __getattribute__(self, k):
        if k in object.__getattribute__(self, "__slots__") or k == "clear":
            return object.__getattribute__(self, k)
        if k == "name":
            return object.__getattribute__(self, "filename")
        if self.fp is None:
            self.fp = open(self.fn, self.mode)
        if k[0] == "_" and (len(k) < 2 or k[1] != "_"):
            k = k[1:]
        return getattr(self.fp, k)

    def clear(self):
        with suppress():
            self.fp.close()
        self.fp = None

class CompatFile(discord.File):

    def __init__(self, fp, filename=None, spoiler=False):
        if type(fp) is bytes:
            fp = io.BytesIO(fp)
        self.fp = self._fp = fp
        if issubclass(type(fp), io.IOBase):
            self.fp = fp
            self._original_pos = fp.tell()
            self._owner = False
        else:
            self.fp = open2(fp, "rb")
            self._original_pos = 0
            self._owner = True
        self._closer = self.fp.close
        self.fp.close = lambda: None
        if filename is None:
            if isinstance(fp, str):
                _, self.filename = os.path.split(fp)
            else:
                self.filename = getattr(fp, 'name', None)
        else:
            self.filename = filename
        if spoiler:
            if self.filename is not None:
                if not self.filename.startswith("SPOILER_"):
                    self.filename = "SPOILER_" + self.filename
            else:
                self.filename = "SPOILER_" + "UNKNOWN"
        elif self.filename.startswith("SPOILER_"):
            self.filename = self.filename[8:]
        self.clear = getattr(self.fp, "clear", lambda self: None)

    def reset(self, seek=True):
        if seek:
            self.fp.seek(self._original_pos)

    def close(self):
        self.fp.close = self._closer
        if self._owner:
            self._closer()

class DownloadingFile(io.IOBase):

    __slots__ = ("fp", "fn", "mode", "filename", "af")

    def __init__(self, fn, af, mode="rb", filename=None):
        self.fp = None
        self.fn = fn
        self.mode = mode
        self.filename = filename or getattr(fn, "name", None) or fn
        self.af = af
        for _ in loop(720):
            if os.path.exists(fn):
                break
            if af():
                raise FileNotFoundError
            time.sleep(0.1)

    def __getattribute__(self, k):
        if k in object.__getattribute__(self, "__slots__") or k in ("seek", "read", "clear"):
            return object.__getattribute__(self, k)
        if k == "name":
            return object.__getattribute__(self, "filename")
        if self.fp is None:
            self.fp = open(self.fn, self.mode)
        if k[0] == "_" and (len(k) < 2 or k[1] != "_"):
            k = k[1:]
        return getattr(self.fp, k)

    def seek(self, pos):
        while os.path.getsize(fn) < pos:
            if self.af():
                break
            time.sleep(0.1)
        self._seek(pos)

    def read(self, size):
        b = self._read(size)
        s = len(b)
        if s < size:
            i = io.BytesIO(b)
            while s < size:
                if self.af():
                    break
                time.sleep(2 / 3)
                b = self._read(size - s)
                s += len(b)
                i.write(b)
            i.seek(0)
            b = i.read()
        return b

    def clear(self):
        with suppress():
            self.fp.close()
        self.fp = None


class ForwardedRequest(io.IOBase):

    __slots__ = ("fp", "resp", "size", "pos", "it")

    def __init__(self, resp, buffer=65536):
        self.resp = resp
        self.it = resp.iter_content(buffer)
        self.fp = io.BytesIO()
        self.size = 0
        self.pos = 0

    def __getattribute__(self, k):
        if k in object.__getattribute__(self, "__slots__") or k in ("seek", "read", "clear"):
            return object.__getattribute__(self, k)
        if k == "name":
            return object.__getattribute__(self, "filename")
        if self.fp is None:
            self.fp = open(self.fn, self.mode)
        if k[0] == "_" and (len(k) < 2 or k[1] != "_"):
            k = k[1:]
        return getattr(self.fp, k)

    def seek(self, pos):
        while self.size < pos:
            try:
                n = next(self.it)
            except StopIteration:
                n = b""
            if not n:
                self.resp.close()
                break
            self.fp.seek(self.size)
            self.size += len(n)
            self.fp.write(n)
        self.fp.seek(pos)
        self.pos = pos

    def read(self, size):
        b = self.fp.read(size)
        s = len(b)
        self.pos += s
        while s < size:
            try:
                n = next(self.it)
            except StopIteration:
                n = b""
            if not n:
                self.resp.close()
                break
            self.fp.seek(self.size)
            self.size += len(n)
            self.fp.write(n)
            self.fp.seek(self.pos)
            b += self.fp.read(size - s)
            s += len(b)
            self.pos += len(b)
        return b

    def clear(self):
        with suppress():
            self.fp.close()
        self.fp = None


class seq(io.IOBase, collections.abc.MutableSequence, contextlib.AbstractContextManager):

    BUF = 262144

    def __init__(self, obj, filename=None):
        self.iter = None
        self.closer = getattr(obj, "close", None)
        if issubclass(type(obj), io.IOBase):
            if issubclass(type(obj), io.BytesIO):
                self.data = obj
            else:
                obj.seek(0)
                self.data = io.BytesIO(obj.read())
                obj.seek(0)
        elif issubclass(type(obj), bytes) or issubclass(type(obj), bytearray) or issubclass(type(obj), memoryview):
            self.data = io.BytesIO(obj)
        elif issubclass(type(obj), collections.abc.Iterator):
            self.iter = iter(obj)
            self.data = io.BytesIO()
            self.high = 0
        elif getattr(obj, "iter_content", None):
            self.iter = obj.iter_content(self.BUF)
            self.data = io.BytesIO()
            self.high = 0
        else:
            raise TypeError(f"a bytes-like object is required, not '{type(obj)}'")
        self.filename = filename
        self.buffer = {}

    def __getitem__(self, k):
        if type(k) is slice:
            out = io.BytesIO()
            start = k.start or 0
            stop = k.stop or inf
            step = k.step or 1
            if step < 0:
                start, stop, step = stop + 1, start + 1, -step
                rev = True
            else:
                rev = False
            curr = start // self.BUF * self.BUF
            offs = start % self.BUF
            out.write(self.load(curr))
            curr += self.BUF
            while curr < stop:
                temp = self.load(curr)
                if not temp:
                    break
                out.write(temp)
                curr += self.BUF
            out.seek(0)
            return out.read()[k]
        base = k // self.BUF
        with suppress(KeyError):
            return self.load(base)[k % self.BUF]
        raise IndexError("seq index out of range")

    def __str__(self):
        if self.filename is None:
            return str(self.data)
        if self.filename:
            return f"<seq name='{self.filename}'>"
        return f"<seq object at {hex(id(self))}"

    def __iter__(self):
        i = 0
        while True:
            x = self[i]
            if x:
                yield x
            else:
                break
            i += 1

    def __getattr__(self, k):
        if k in ("data", "filename"):
            return self.data
        return object.__getattribute__(self.data, k)

    close = lambda self: self.closer() if self.closer else None
    __exit__ = lambda self, *args: self.close()

    def load(self, k):
        with suppress(KeyError):
            return self.buffer[k]
        seek = getattr(self.data, "seek", None)
        if seek:
            if self.iter is not None and k + self.BUF >= self.high:
                seek(self.high)
                with suppress(StopIteration):
                    while k + self.BUF >= self.high:
                        temp = next(self.iter)
                        self.data.write(temp)
                        self.high += len(temp)
            seek(k)
            self.buffer[k] = self.data.read(self.BUF)
        else:
            with suppress(StopIteration):
                while self.high < k:
                    temp = next(self.data)
                    if not temp:
                        return b""
                    self.buffer[self.high] = temp
                    self.high += self.BUF
        return self.buffer.get(k, b"")


class Stream(io.IOBase):

    BUF = 262144
    resp = None

    def __init__(self, url):
        self.url = url
        self.buflen = 0
        self.buf = io.BytesIO()
        self.reset()
        self.refill()

    def reset(self):
        if self.resp:
            with suppress():
                self.resp.close()
        self.resp = requests.get(url, stream=True)
        if BOT[0]:
            BOT[0].activity += 1
        self.iter = self.resp.iter_content(self.BUF)

    def refill(self):
        att = 0
        while self.buflen < self.BUF * 4:
            try:
                self.buf.write(next(self.iter))
            except StopIteration:
                with suppress():
                    self.resp.close()
                return
            except:
                if att > 16:
                    raise
                att += 1
                self.reset()
        with suppress():
            self.resp.close()


# Manages both sync and async get requests.
class RequestManager(contextlib.AbstractContextManager, contextlib.AbstractAsyncContextManager, collections.abc.Callable):

    session = None
    semaphore = Semaphore(512, 256, delay=0.25)

    @classmethod
    def header(cls):
        return {
            "User-Agent": f"Mozilla/5.{xrand(1, 10)}",
            "DNT": "1",
            "X-Forwarded-For": ".".join(str(xrand(1, 255)) for _ in loop(4)),
        }
    headers = header

    async def _init_(self):
        self.session = aiohttp.ClientSession(loop=eloop)

    async def aio_call(self, url, headers, files, data, method, decode=False, json=False):
        if files is not None:
            raise NotImplementedError("Unable to send multipart files asynchronously.")
        async with self.semaphore:
            async with getattr(self.session, method)(url, headers=headers, data=data) as resp:
                if BOT[0]:
                    BOT[0].activity += 1
                if resp.status >= 400:
                    data = await resp.read()
                    raise ConnectionError(resp.status, url, as_str(data))
                if json:
                    return await resp.json()
                data = await resp.read()
                if decode:
                    return as_str(data)
                return data

    def __call__(self, url, headers={}, files=None, data=None, raw=False, timeout=8, method="get", decode=False, json=False, bypass=True, aio=False):
        if bypass:
            if "user-agent" not in headers and "User-Agent" not in headers:
                headers["User-Agent"] = f"Mozilla/5.{xrand(1, 10)}"
            headers["DNT"] = "1"
        method = method.casefold()
        if aio:
            return create_task(asyncio.wait_for(self.aio_call(url, headers, files, data, method, decode, json), timeout=timeout))
        with self.semaphore:
            with getattr(requests, method)(url, headers=headers, files=files, data=data, stream=True, timeout=timeout) as resp:
                if BOT[0]:
                    BOT[0].activity += 1
                if resp.status_code >= 400:
                    raise ConnectionError(resp.status_code, url, resp.text)
                if json:
                    return resp.json()
                if raw:
                    data = resp.raw.read()
                else:
                    data = resp.content
                if decode:
                    return as_str(data)
                return data

    def __exit__(self, *args):
        self.session.close()

    def __aexit__(self, *args):
        self.session.close()
        return async_nop()

Request = RequestManager()
create_task(Request._init_())


def load_emojis():
    global emoji_translate, emoji_replace, em_trans
    with tracebacksuppressor:
        resp = Request("https://emojipedia.org/twitter", decode=True, timeout=None)
        lines = resp.split('<ul class="emoji-grid">', 1)[-1].rsplit("</ul>", 1)[0].strip().split("</a>")
        urls = [line.split('srcset="', 1)[-1].split('"', 1)[0].split(None, 1)[0].replace("/144/", "/160/", 1) for line in lines if 'srcset="' in line]
        e_ids = [url.rsplit("_", 1)[-1].split(".", 1)[0].split("-") for url in urls]
        emojis = ["".join(chr(int(i, 16)) for i in e_id) for e_id in e_ids]
        etrans = dict(zip(emojis, urls))

        # resp = Request("https://raw.githubusercontent.com/twitter/twemoji/master/src/test/preview-svg.html", decode=True, timeout=None)
        # emojis = [html_decode(line) for line in lines]
        # e_ids = ["-".join(hex(ord(c))[2:] for c in emoji) for emoji in emojis]
        # etrans = {k: f"https://github.com/twitter/twemoji/raw/master/assets/72x72/{v}.png" for k, v in zip(emojis, e_ids)}

        # resp = Request("https://raw.githubusercontent.com/BreadMoirai/DiscordEmoji/master/src/main/java/com/github/breadmoirai/Emoji.java", decode=True, timeout=None)
        # e_resp = [line.strip()[:-1] for line in resp[resp.index("public enum Emoji {") + len("public enum Emoji {"):resp.index("private static final Emoji[] SORTED;")].strip().split("\n")]
        # etrans = {literal_eval(words[0]).encode("utf-16", "surrogatepass").decode("utf-16"): f" {literal_eval(words[2][:-1])} " for emoji in e_resp for words in (emoji.strip(";")[emoji.index("\\u") - 1:].split(","),) if words[2][:-1].strip() != "null"}
        # with open("misc/emojis.txt", "r", encoding="utf-8") as f:
        #     resp = f.read()
        # etrans.update({k: v for k, v in (line.split(" ", 1) for line in resp.splitlines())})

        emoji_translate = {k: v for k, v in etrans.items() if len(k) == 1}
        emoji_replace = {k: v for k, v in etrans.items() if len(k) > 1}
        em_trans = "".maketrans(emoji_translate)
        print(f"Successfully loaded {len(etrans)} unicode emojis.")

def translate_emojis(s):
    return s.translate(em_trans)

def replace_emojis(s):
    for emoji, url in emoji_replace.items():
        if emoji in s:
            s = s.replace(emoji, url)
    return s

def find_emojis_ex(s):
    out = deque()
    for emoji, url in emoji_replace.items():
        if emoji in s:
            out.append(url[1:-1])
    for emoji, url in emoji_translate.items():
        if emoji in s:
            out.append(url[1:-1])
    return list(set(out))


# Stores and manages timezones information.
TIMEZONES = cdict()

def load_timezones():
    with tracebacksuppressor():
        with open("misc/timezones.txt", "rb") as f:
            data = as_str(f.read())
            for line in data.splitlines():
                info = line.split("\t")
                abb = info[0].casefold()
                if len(abb) >= 3 and (abb not in TIMEZONES or "(unofficial)" not in info[1]):
                    temp = info[-1].replace("\\", "/")
                    curr = sorted([round((1 - (i[3] == "−") * 2) * (time_parse(i[4:]) if ":" in i else float(i[4:]) * 60) * 60) for i in temp.split("/") if i.startswith("UTC")])
                    if len(curr) == 1:
                        curr = curr[0]
                    TIMEZONES[abb] = curr
            print(f"Successfully loaded {len(TIMEZONES)} timezones.")

def is_dst(dt=None, timezone="UTC"):
    if dt is None:
        dt = utc_dt()
    timezone = pytz.timezone(timezone)
    timezone_aware_date = timezone.localize(dt, is_dst=None)
    return timezone_aware_date.tzinfo._dst.seconds != 0

def get_timezone(tz):
    s = TIMEZONES[tz]
    if issubclass(type(s), collections.abc.Collection):
        return s[is_dst(timezone=tz.upper())]
    return s

def as_timezone(tz):
    if not tz:
        raise KeyError
    with suppress(KeyError):
        return round((city_time(tz).timestamp() - utc()) / 60) * 60
    a = tz
    h = 0
    for op in ("+-"):
        with suppress(ValueError):
            i = a.index(op)
            h += float(a[i:])
            a = a[:i]
            break
    tz = a.casefold()
    return round_min(get_timezone(tz) + h * 3600)

def timezone_repr(tz):
    if tz in ZONES:
        return capwords(tz)
    return tz.upper()

def parse_with_now(expr):
    if not expr or expr.strip().casefold() == "now":
        return utc_ddt()
    bc = False
    if expr[-3:].casefold() == " ad":
        expr = expr[:-3]
    elif expr[-5:].casefold() == " a.d.":
        expr = expr[:-5]
    if expr[-3:].casefold() == " bc":
        expr = expr[:-3]
        bc = True
    elif expr[-5:].casefold() == " b.c.":
        expr = expr[:-5]
        bc = True
    try:
        dt = tparser.parse(expr).replace(tzinfo=datetime.timezone.utc)
    except Exception as ex:
        print(ex)
        s = str(ex).split(":", 1)[0]
        if s.startswith("year "):
            s = s[5:]
            if s.endswith(" is out of range"):
                s = s[:-16]
                y = int(s)
                if bc:
                    y = -y
                offs, year = divmod(y, 400)
                offs = offs * 400 - 2000
                year += 2000
                expr = regexp("0*" + s).sub(str(year), expr, 1)
                return DynamicDT.fromdatetime(tparser.parse(expr)).set_offset(offs)
        elif s.startswith("Python int too large to convert to C"):
            y = int(regexp("[0-9]{10,}").findall(expr)[0])
            if bc:
                y = -y
            offs, year = divmod(y, 400)
            offs = offs * 400 - 2000
            year += 2000
            expr = regexp("[0-9]{10,}").sub(str(year), expr, 1)
            return DynamicDT.fromdatetime(tparser.parse(expr)).set_offset(offs)
        elif s.startswith("Unknown string format") or s.startswith("month must be in"):
            try:
                y = int(regexp("[0-9]{5,}").findall(expr)[0])
            except IndexError:
                y = None
            if y is None:
                raise
            if bc:
                y = -y
            offs, year = divmod(y, 400)
            offs = offs * 400 - 2000
            year += 2000
            expr = regexp("[0-9]{5,}").sub(str(year), expr, 1)
            return DynamicDT.fromdatetime(tparser.parse(expr)).set_offset(offs)
        raise
    if bc:
        y = -dt.year
        offs, year = divmod(y, 400)
        offs = offs * 400 - 2000
        year += 2000
        return DynamicDT.fromdatetime(dt.replace(year=year)).set_offset(offs)
    return DynamicDT.fromdatetime(dt)

# Parses a time expression, with an optional timezone input at the end.
def tzparse(expr):
    try:
        s = float(expr)
    except ValueError:
        expr = expr.strip()
        day = None
        if "today" in expr:
            day = 0
            expr = expr.replace("today", "")
        elif "tomorrow" in expr:
            day = 1
            expr = expr.replace("tomorrow", "")
        elif "yesterday" in expr:
            day = -1
            expr = expr.replace("yesterday", "")
        if " " in expr:
            t = 0
            try:
                args = shlex.split(expr)
            except ValueError:
                args = expr.split()
            for i in (0, -1):
                arg = args[i]
                with suppress(KeyError):
                    t = as_timezone(arg)
                    args.pop(i)
                    expr = " ".join(args)
                    break
                h = 0
            t = parse_with_now(expr) - (h * 3600 + t)
        else:
            t = parse_with_now(expr)
        if day is not None:
            curr = utc_ddt() + day * 86400
            one_day = 86400
            while t < curr:
                t += one_day
            while (t - curr).total_seconds() > one_day:
                t -= one_day
        return t
    if not is_finite(s) or abs(s) >= 1 << 31:
        s = int(expr.split(".", 1)[0])
    return utc_dft(s)


def smart_split(s):
    t = shlex.shlex(s)
    t.whitespace_split = True
    out = deque()
    while True:
        try:
            w = t.get_token()
        except ValueError:
            out.append(t.token.strip(t.quotes))
            break
        if not w:
            break
        out.extend(shlex.split(w))
    return alist(out)


__filetrans = {
    "\\": "_",
    "/": "_",
    " ": "%20",
    ":": "=",
    "*": "-",
    "?": "&",
    '"': "^",
    "<": "{",
    ">": "}",
    "|": "!",
}
filetrans = "".maketrans(__filetrans)


# Basic inheritable class for all bot commands.
class Command(collections.abc.Hashable, collections.abc.Callable):
    description = ""
    usage = ""
    min_level = 0
    rate_limit = 0

    def perm_error(self, perm, req=None, reason=None):
        if req is None:
            req = self.min_level
        if reason is None:
            reason = f"for command {self.name[-1]}"
        return PermissionError(f"Insufficient priviliges {reason}. Required level: {req}, Current level: {perm}.")

    def __init__(self, bot, catg):
        self.used = {}
        if not hasattr(self, "data"):
            self.data = cdict()
        if not hasattr(self, "min_display"):
            self.min_display = self.min_level
        if not hasattr(self, "name"):
            self.name = []
        self.__name__ = self.__class__.__name__
        if not hasattr(self, "alias"):
            self.alias = self.name
        else:
            self.alias.append(self.parse_name())
        self.name.append(self.parse_name())
        self.aliases = {full_prune(alias).replace("*", "").replace("_", "").replace("||", ""): alias for alias in self.alias}
        self.aliases.pop("", None)
        for a in self.aliases:
            if a in bot.commands:
                bot.commands[a].add(self)
            else:
                bot.commands[a] = alist((self,))
        self.catg = catg
        self.bot = bot
        self._globals = bot._globals
        f = getattr(self, "__load__", None)
        if callable(f):
            try:
                f()
            except:
                print_exc()
                self.data.clear()
                f()

    __hash__ = lambda self: hash(self.parse_name()) ^ hash(self.catg)
    __str__ = lambda self: f"Command <{self.parse_name()}>"
    __call__ = lambda self, **void: None

    parse_name = lambda self: self.__name__.strip("_")
    parse_description = lambda self: self.description.replace('⟨MIZA⟩', self.bot.user.name).replace('⟨WEBSERVER⟩', self.bot.webserver)

    def unload(self):
        bot = self.bot
        for alias in self.alias:
            alias = alias.replace("*", "").replace("_", "").replace("||", "")
            coms = bot.commands.get(alias)
            if coms:
                coms.remove(self)
                print("unloaded", alias, "from", self)
            if not coms:
                bot.commands.pop(alias, None)


# Basic inheritable class for all bot databases.
class Database(collections.abc.MutableMapping, collections.abc.Hashable, collections.abc.Callable):
    bot = None
    rate_limit = 3
    name = "data"

    def __init__(self, bot, catg):
        name = self.name
        self.__name__ = self.__class__.__name__
        fhp = "saves/" + name
        if not getattr(self, "no_file", False):
            if os.path.exists(fhp):
                data = self.data = FileHashDict(path=fhp)
            else:
                self.file = fhp + ".json"
                self.updated = False
                try:
                    with open(self.file, "rb") as f:
                        s = f.read()
                    if not s:
                        raise FileNotFoundError
                    try:
                        data = select_and_loads(s, mode="unsafe")
                    except:
                        print(self.file)
                        print_exc()
                        raise FileNotFoundError
                    data = FileHashDict(data, path=fhp)
                    data.modified.update(data.data.keys())
                    self.data = data
                except FileNotFoundError:
                    data = None
        else:
            data = self.data = {}
        if data is None:
            self.data = FileHashDict(path=fhp)
        if not issubclass(type(self.data), collections.abc.MutableMapping):
            self.data = FileHashDict(dict.fromkeys(self.data), path=fhp)
        bot.database[name] = bot.data[name] = self
        self.catg = catg
        self.bot = bot
        self._semaphore = Semaphore(1, 1, delay=0.5, rate_limit=self.rate_limit)
        self._garbage_semaphore = Semaphore(1, 0, delay=3, rate_limit=self.rate_limit * 3 + 30)
        self._globals = globals()
        f = getattr(self, "__load__", None)
        if callable(f):
            try:
                f()
            except:
                print_exc()
                self.data.clear()
                f()

    __hash__ = lambda self: hash(self.__name__)
    __str__ = lambda self: f"Database <{self.__name__}>"
    __call__ = lambda self: None
    __len__ = lambda self: len(self.data)
    __iter__ = lambda self: iter(self.data)
    __contains__ = lambda self, k: k in self.data
    __eq__ = lambda self, other: self.data == other
    __ne__ = lambda self, other: self.data != other

    def __setitem__(self, k, v):
        self.data[k] = v
        return self
    def __getitem__(self, k):
        return self.data[k]
    def __delitem__(self, k):
        return self.data.__delitem__(k)

    keys = lambda self: self.data.keys()
    items = lambda self: self.data.items()
    values = lambda self: self.data.values()
    get = lambda self, *args, **kwargs: self.data.get(*args, **kwargs)
    pop = lambda self, *args, **kwargs: self.data.pop(*args, **kwargs)
    popitem = lambda self, *args, **kwargs: self.data.popitem(*args, **kwargs)
    clear = lambda self: self.data.clear()
    setdefault = lambda self, k, v: self.data.setdefault(k, v)
    keys = lambda self: self.data.keys()
    discard = lambda self, k: self.data.pop(k, None)

    def update(self, modified=None, force=False):
        if hasattr(self, "no_file"):
            return
        if force:
            try:
                limit = getattr(self, "limit", None)
                if limit and len(self) > limit:
                    print(f"{self} overflowed by {len(self) - limit}, dropping...")
                    with tracebacksuppressor:
                        while len(self) > limit:
                            self.pop(next(iter(self)))
                self.data.__update__()
            except:
                print(self, traceback.format_exc(), sep="\n", end="")
        else:
            if modified is None:
                self.data.modified = set(self.data.keys())
            else:
                if issubclass(type(modified), collections.abc.Sized) and type(modified) not in (str, bytes):
                    self.data.modified.update(modified)
                else:
                    self.data.modified.add(modified)
        return False

    def unload(self):
        self.unloaded = True
        bot = self.bot
        func = getattr(self, "_destroy_", None)
        if callable(func):
            await_fut(create_future(func, priority=True))
        for f in dir(self):
            if f.startswith("_") and f[-1] == "_" and f[1] != "_":
                func = getattr(self, f, None)
                if callable(func):
                    bot.events[f].remove(func)
                    print("unloaded", f, "from", self)
        self.update(force=True)
        bot.data.pop(self, None)
        bot.database.pop(self, None)
        self.data.clear()


class ImagePool:
    usage = "<verbose{?v}>?"
    flags = "v"
    rate_limit = (0.05, 0.25)
    threshold = 1024

    async def __call__(self, bot, channel, flags, **void):
        url = await bot.data.imagepools.get(self.database, self.fetch_one, self.threshold)
        if "v" in flags:
            return escape_roles(url)
        self.bot.send_as_embeds(channel, image=url)


# Redirects all print operations to target files, limiting the amount of operations that can occur in any given amount of time for efficiency.
class __logPrinter:

    def __init__(self, file=None):
        self.buffer = self
        self.data = {}
        self.history = {}
        self.counts = {}
        self.funcs = alist()
        self.file = file
        self.closed = True

    def start(self):
        self.exec = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.future = self.exec.submit(self.update_print)
        self.closed = False

    def file_print(self, fn, b):
        try:
            if type(fn) not in (str, bytes):
                f = fn
            elif type(b) in (bytes, bytearray):
                f = open(fn, "ab")
            elif type(b) is str:
                f = open(fn, "a", encoding="utf-8")
            else:
                f = fn
            with closing(f):
                try:
                    f.write(b)
                except TypeError:
                    try:
                        f.write(as_str(b))
                    except ValueError:
                        pass
        except:
            sys.__stdout__.write(traceback.format_exc())

    def flush(self):
        outfunc = lambda s: self.file_print(self.file, s)
        enc = lambda x: bytes(x, "utf-8")
        try:
            for f in tuple(self.data):
                if not self.data[f]:
                    self.data.pop(f)
                    continue
                out = lim_str(self.data[f], 65536)
                data = enc(self.data[f])
                self.data[f] = ""
                if self.funcs:
                    [func(out) for func in self.funcs]
                if f == self.file:
                    outfunc(data)
                else:
                    self.file_print(f, data)
        except:
            sys.__stdout__.write(traceback.format_exc())

    def update_print(self):
        if self.file is None:
            return
        while True:
            with Delay(1):
                self.flush()
            while not os.path.exists("common.py") or self.closed:
                time.sleep(0.5)

    def __call__(self, *args, sep=" ", end="\n", prefix="", file=None, **void):
        out = str(sep).join(i if type(i) is str else str(i) for i in args) + str(end) + str(prefix)
        if not out:
            return
        if self.closed or args and type(args[0]) is str and args[0].startswith("WARNING:"):
            return sys.__stdout__.write(out)
        if file is None:
            file = self.file
        if file not in self.data:
            self.data[file] = ""
        temp = out.strip()
        if temp:
            if file in self.history and self.history.get(file).strip() == temp:
                add_dict(self.counts, {file:1})
                return
            elif self.counts.get(file):
                count = self.counts.pop(file)
                times = "s" if count != 1 else ""
                out, self.history[file] = f"<Last message repeated {count} time{times}>\n{out}", out
            else:
                self.history[file] = out
                self.counts.pop(file, None)
        self.data[file] += out
        return sys.__stdout__.write(out)

    def write(self, *args, end="", **kwargs):
        args2 = [as_str(arg) for arg in args]
        return self.__call__(*args2, end=end, **kwargs)

    read = lambda self, *args, **kwargs: bytes()
    close = lambda self, force=False: self.__setattr__("closed", force)
    isatty = lambda self: False


create_future_ex(load_mimes)
PRINT = __logPrinter("log.txt")

# Sets all instances of print to the custom print implementation.

# sys.stdout = sys.stderr = print
# for mod in (discord, concurrent.futures, asyncio.futures, asyncio, psutil, subprocess, tracemalloc):
#     builtins = getattr(mod, "__builtins__", None)
#     if builtins:
#         builtins["print"] = print