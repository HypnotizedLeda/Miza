try:
    from common import *
except ModuleNotFoundError:
    import os, sys
    sys.path.append(os.path.abspath('..'))
    os.chdir("..")
    from common import *


HOST = "https://mizabot.xyz"
PORT = AUTH.get("webserver_port", 80)
IND = "\x7f"


def send(*args, escape=True):
    try:
        s = " ".join(str(i) for i in args)
        if escape:
            s = "\x00" + s
        if s:
            if s[-1] != "\n":
                s += "\n"
            s = s.encode("utf-8")
            sys.stdout.buffer.write(s)
            sys.__stderr__.buffer.write(s)
            sys.__stderr__.flush()
    except OSError:
        psutil.Process().kill()


def create_etag(data):
    s = str(ihash(data[:128] + data[-128:]) + len(data) & 4294967295)
    return '"' + "0" * (10 - len(s)) + s + '"'


SEMAPHORES = {}
STATIC = {}
TZCACHE = {}
RESPONSES = {}
RESPONSES[0] = cdict(set_result=lambda *args: None)

PREVIEW = {}
prev_date = utc_dt().date()
zfailed = set()


import cherrypy
from cherrypy._cpdispatch import Dispatcher
cp = cherrypy

class EndpointRedirects(Dispatcher):

    def __call__(self, path):
        send("@@@", escape=False)
        if path == "/favicon.ico":
            path = "/favicon"
        elif path[1:] == AUTH.get("discord_token"):
            path = "/backup"
        elif path == "/ip":
            path = "/get_ip"
        elif path[:3] == "/f/":
            path = "/files/" + path[3:]
        return Dispatcher.__call__(self, path)

config = {
    "global": {
        "server.socket_host": "0.0.0.0",
        "server.socket_port": PORT,
        "server.thread_pool": 32,
        "server.max_request_body_size": 0,
        "server.socket_timeout": 60,
    },
    "/": {
        "request.dispatch": EndpointRedirects(),
    }
}

if os.path.exists("misc/cert.pem") and os.path.exists("misc/private.key.pem"):
    config["global"]["server.ssl_module"] = "builtin"
    config["global"]["server.ssl_certificate"] = "domain.cert.pem"
    config["global"]["server.ssl_private_key"] = "private.key.pem"
    config["global"]["server.ssl_certificate_chain"] = "intermediate.cert.pem"

HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Server": "Miza",
    "Vary": "Accept-Encoding",
    "Accept-Ranges": "bytes",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "*",
    "Access-Control-Allow-Origin": "*",
}

CHEADERS = {"Cache-Control": "public, max-age=3600, stale-while-revalidate=1073741824, stale-if-error=1073741824"}
SHEADERS = {"Cache-Control": "public, max-age=30, stale-while-revalidate=1073741824, stale-if-error=1073741824"}

CHEADERS.update(HEADERS)
SHEADERS.update(HEADERS)


def fetch_static(path, ignore=False):
    while path.startswith("../"):
        path = path[3:]
    try:
        try:
            data = STATIC[path]
        except KeyError:
            fn = f"misc/{path}"
            fn2 = fn.rsplit(".", 1)[0] + ".zip"
            if os.path.exists(fn2) and zipfile.is_zipfile(fn2):
                with ZipFile(fn2, compression=zipfile.ZIP_DEFLATED, allowZip64=True, strict_timestamps=False) as z:
                    data = z.read(path.rsplit("/", 1)[-1])
            else:
                with open(fn, "rb") as f:
                    data = f.read()
            STATIC[path] = data
        fmt = path.rsplit(".", 1)[-1].casefold()
        try:
            mime = MIMES[fmt]
        except KeyError:
            mime = "text/html"
        return data, mime
    except:
        if not ignore:
            send(path)
            send(traceback.format_exc())
        raise

est_time = utc()
est_last = -inf

def estimate_life():
    global est_time, est_last
    with tracebacksuppressor:
        hosted = sorted(int(f[1:].split("~", 1)[0]) / 1e6 for f in os.listdir("cache") if f.startswith(IND))
        if not hosted:
            est_last = -inf
            ts = 0
        else:
            ts = hosted[0]
        t = ts_us()
        while t in RESPONSES:
            t += 1
        RESPONSES[t] = fut = concurrent.futures.Future()
        send(f"!{t}\x7fbot.storage_ratio", escape=False)
        j, after = fut.result()
        RESPONSES.pop(t, None)
        try:
            last = (utc() - ts) / j.get("result", 1)
        except ZeroDivisionError:
            last = inf
        send(last)
        est_time = utc() - last
        est_last = utc()

estimate_life_after = lambda t: time.sleep(t) or estimate_life()

# create_future_ex(estimate_life_after, 10)

geo_sem = Semaphore(90, 256, rate_limit=60)
geo_count = 0

def get_geo(ip):
    global geo_count
    try:
        resp = TZCACHE[ip]
    except KeyError:
        if geo_count & 1:
            url = f"http://ip-api.com/json/{ip}?fields=256"
        else:
            url = f"https://demo.ip-api.com/json/{ip}?fields=256&key=test-demo-pro"
        geo_count += 1
        with geo_sem:
            resp = requests.get(url, headers={"DNT": "1", "User-Agent": f"Mozilla/5.{ip[-1]}", "Origin": "https://members.ip-api.com"})
        send("@@@", escape=False)
        resp.raise_for_status()
        TZCACHE[ip] = resp = resp.json()
        send(ip + "\t" + "\t".join(resp.values()))
    return resp

last_image = [None] * 2


class Server:

    @cp.expose
    def fileinfo(self, path, **void):
        orig_path = path
        ind = IND
        p = None
        cp.response.headers.update(SHEADERS)
        if path.startswith("!"):
            ind = "!"
            path = path[1:]
        elif not path.startswith("@"):
            b = path.lstrip("~").split(".", 1)[0].encode("utf-8") + b"=="
            if (len(b) - 1) & 3 == 0:
                b += b"="
            path = str(int.from_bytes(base64.urlsafe_b64decode(b), "big"))
        if not p:
            p = find_file(path, ind=ind)
        mime = get_mime(p)
        f_url = cp.url(qs=cp.request.query_string).replace("/fileinfo/", "/f/")
        st = os.stat(p)
        fn = p.rsplit("/", 1)[-1].split("~", 1)[-1].rstrip(IND)
        t = utc()
        ti = max(st.st_atime + 30 * 86400, st.st_ctime + 60 * 86400, t)
        d = dict(
            id=p.rsplit("/", 1)[-1].split("~", 1)[0].lstrip(IND),
            filename=fn,
            ttl=ti - t,
            size=st.st_size,
            mimetype=mime,
            raw=f_url,
            dl=f_url.replace("/f/", "/d/", 1),
        )
        if p.endswith("~.forward$") and mime == "text/html":
            with open(p, "r", encoding="utf-8") as f:
                resp = f.read(1048576)
            s = resp
            search = "<!DOCTYPE HTML><!--"
            if s.startswith(search):
                s = s[len(search):]
                search = '--><html><meta http-equiv="refresh" content="0; URL='
                try:
                    s = s[:s.index(search)]
                except ValueError:
                    pass
                else:
                    url, code, ftype = json.loads(s)
                    d["original_url"] = url
        return json.dumps(d).encode("utf-8")

    @cp.expose(("preview", "p", "animate", "animation", "a", "images", "image", "i", "view", "v", "files", "file", "f", "download", "d"))
    def files(self, path, filename=None, download=None, **void):
        if path in ("hacks", "mods", "files", "download", "static"):
            send(cp.request.remote.ip + " was rickrolled 🙃")
            raise cp.HTTPRedirect("https://www.youtube.com/watch?v=dQw4w9WgXcQ", status=301)
        orig_path = path
        ind = IND
        p = None
        cp.response.headers.update(CHEADERS)
        if path.startswith("!"):
            ind = "!"
            path = path[1:]
        elif not path.startswith("@"):
            b = path.lstrip("~").split(".", 1)[0].encode("utf-8") + b"=="
            if b.startswith(b"dQ"):
                c = b[2:]
                if (len(c) - 1) & 3 == 0:
                    c += b"="
                path = str(int.from_bytes(base64.urlsafe_b64decode(c), "big"))
                try:
                    p = find_file(path, ind=ind)
                except FileNotFoundError:
                    pass
                else:
                    url = cp.request.base + "/i/" + c.rstrip(b"=").decode("utf-8", "replace")
                    return f"""<!DOCTYPE html>
<html><head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<meta property="og:type" content="video.other">
<meta property="twitter:player" content="https://www.youtube.com/embed/dQw4w9WgXcQ">
<meta property="og:video:type" content="text/html">
<meta property="og:video:width" content="960">
<meta property="og:video:height" content="720">
<meta name="twitter:image" content="{url}">
<meta http-equiv="refresh" content="0;url=https://www.youtube.com/watch?v=dQw4w9WgXcQ">
</head><body></body></html>"""
            if (len(b) - 1) & 3 == 0:
                b += b"="
            path = str(int.from_bytes(base64.urlsafe_b64decode(b), "big"))
        if not p:
            p = find_file(path, ind=ind)
        sem = SEMAPHORES.get(p)
        if not sem:
            while len(SEMAPHORES) >= 4096:
                sem = SEMAPHORES.pop(next(iter(SEMAPHORES)))
                if sem.is_busy():
                    raise SemaphoreOverflowError
            sem = SEMAPHORES[p] = Semaphore(256, 256, rate_limit=60)
        with sem:
            endpoint = cp.url(qs=cp.request.query_string, base="")[1:].split("/", 1)[0]
            download = download and download[0] not in "0fFnN" or endpoint.startswith("d")
            if download:
                mime = MIMES.get(p.rsplit("/", 1)[-1].rsplit(".", 1)[-1])
            else:
                mime = get_mime(p)
            st = os.stat(p)
            fn = p.rsplit("/", 1)[-1].split("~", 1)[-1].rstrip(IND)
            attachment = filename or fn
            cp.response.headers["Attachment-Filename"] = attachment
            if endpoint.startswith("p"):
                s = """<!DOCTYPE html>
<html>
    <head>
        <style>
        body {
            text-align: center;
            font-family: 'Comic Sans MS';
        }
        img {
            margin-top: 32px;
            display: block;
            margin-left: auto;
            margin-right: auto;
        }
        a:link {
            color: #ffff00;
            text-decoration: none;
        }
        a:visited {
            color: #ffff00;
            text-decoration: none;
        }
        a:hover {
            color: #ff0000;
            text-decoration: underline;
        }
        a:active {
            color: #00ff00;
            text-decoration: underline;
        }
        </style>"""
                f_url = cp.url(qs=cp.request.query_string).replace("/preview/", "/p/")
                o_url = HOST + cp.url(qs=cp.request.query_string, base="").replace("/preview/", "/p/")
                s_url = f_url.replace("/p/", "/f/")
                i_url = f_url.replace("/p/", "/i/")
                url = o_url.replace("/p/", "/f/")
                s += f"""
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
        <meta name="twitter:image:src" content="{i_url}">
        <meta name="twitter:card" content="summary_large_image">
        <meta name="twitter:title" content="{attachment}">
        <meta property="og:image" content="{i_url}">
    </head>
    <body style="background-color:black;">
        <h1 style="color:white;">{attachment}</h1>"""
                t = utc()
                ti = max(st.st_atime + 30 * 86400, st.st_ctime + 60 * 86400, t)
                s += f"""
                <p style="color:#00ffff;">File size: {byte_scale(st.st_size)}B</p>
                <p style="color:#bf7fff;">Estimated file lifetime: {sec2time(ti - t)}</p>"""
                s += f'\n<a href="{url}">{url}<br></a>'
                preview = deque()
                if mime.startswith("image/"):
                    preview.append(f'<img width="480" src="{s_url}" alt="{url.rsplit("/", 1)[-1]}">')
                elif mime.startswith("audio/"):
                    preview.append(f'<div align="center"><audio controls><source src="{s_url}" type="{mime}"></audio></div>')
                elif mime.startswith("video/"):
                    preview.append(f'<div align="center"><video width="480" playsinline controls><source src="{s_url}" type="{mime}"></video></div>')
                elif mime.startswith("text/"):
                    preview.append(f'<a href="{url}">{url}<br></a>')
                preview.append(f'<a style="color:#0000ff;" href="{s_url.replace("/f/", "/d/")}">Download</a>')
                if not preview:
                    preview.append(f'<img src="{cp.request.base}/static/hug.gif" alt="Miza-Dottie-Hug" style="width:14.2857%;height:14.2857%;">')
                s += "\n" + "\n".join(preview)
                s += f"""
        <p><a style="color:#bfffbf;" href="{o_url}">Share this page!</a></p>""" + """
        <p><a style="color:#7fffff;" href="/upload">Back to main file host</a></p>
    </body>
</html>"""
                b = s.encode("utf-8", "replace")
                cp.response.headers["Content-Type"] = "text/html"
                cp.response.headers["Content-Length"] = len(b)
                cp.response.headers["ETag"] = create_etag(b)
                return b
            elif endpoint.startswith("i") and (mime in ("image/webp", "image/gif", "image/apng") or mime.split("/", 1)[0] == "video"):
                if p != last_image[0]:
                    args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-err_detect", "ignore_err", "-fflags", "+discardcorrupt+fastseek+genpts+igndts+flush_packets", "-an", "-i", p, "-frames:v", "1", "-f", "image2", "-c:v", "png", "-"]
                    proc = psutil.Popen(args, stdout=subprocess.PIPE)
                    b = proc.stdout.read()
                    last_image[:] = p, b
                    try:
                        proc.kill()
                    except:
                        pass
                else:
                    b = last_image[-1]
                cp.response.headers["Content-Type"] = "image/png"
                cp.response.headers["Content-Length"] = len(b)
                cp.response.headers["ETag"] = create_etag(b)
                return b
            elif endpoint.startswith("a") and mime.split("/", 1)[0] in "video":
                f_url = cp.url(qs=cp.request.query_string).replace(f"/{endpoint}/", "/f/")
                i_url = f_url.replace("/f/", "/i/")
                b = ("""<!DOCTYPE html>
<html>
<style>
.center {
  margin: 0;
  position: absolute;
  top: 50%;
  left: 50%;
  -ms-transform: translate(-50%, -50%);
  transform: translate(-50%, -50%);
}
</style>""" + f"""
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<meta name="twitter:image:src" content="{i_url}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{attachment}">
<meta property="og:image" content="{i_url}">
<body style="background-color:black;">
<video class="center" playsinline autoplay muted loop>
  <source src="{f_url}">
</video>
</body>
</html>""").encode("utf-8")
                cp.response.headers["Content-Type"] = "text/html"
                cp.response.headers["Content-Length"] = len(b)
                cp.response.headers["ETag"] = create_etag(b)
                return b
            elif not os.path.exists(p):
                raise FileNotFoundError(p)
            elif not download and p.endswith("~.forward$") and mime == "text/html":
                with open(p, "r", encoding="utf-8") as f:
                    resp = f.read(1048576)
                s = resp
                search = "<!DOCTYPE HTML><!--"
                if s.startswith(search):
                    s = s[len(search):]
                    search = '--><html><meta http-equiv="refresh" content="0; URL='
                    try:
                        s = s[:s.index(search)]
                    except ValueError:
                        pass
                    else:
                        url, code, ftype = json.loads(s)
                        if ftype == 1:
                            data = resp.encode("utf-8")
                            cp.response.headers["Location"] = url
                            cp.response.headers["Content-Type"] = mime
                            cp.response.headers["Content-Length"] = len(data)
                            cp.response.headers["ETag"] = create_etag(data)
                            cp.response.status = int(code)
                            return data
                        elif ftype == 2:
                            headers = fcdict(cp.request.headers)
                            headers.pop("Remote-Addr", None)
                            headers.pop("Host", None)
                            headers.update(Request.header())
                            resp = requests.get(url, headers=headers, stream=True)
                            resp.raw.decode_content = False
                            headers = fcdict(resp.headers)
                            cd = headers.get("Content-Disposition")
                            if cd:
                                if not download:
                                    headers["Content-Disposition"] = cd.replace("attachment;", "").strip()
                                elif "attachment" not in cd:
                                    headers["Content-Disposition"] = "attachment;" + cd
                            elif download:
                                headers["Content-Disposition"] = "attachment"
                            cp.response.headers.update(("-".join(w.capitalize() for w in k.split("-")), v) for k, v in headers.items())
                            send(s)
                            send(headers)
                            send(cp.response.headers)
                            cp.response.status = int(resp.status_code)
                            if float(fcdict(resp.headers).get("Content-Length", inf)) <= 8388608:
                                b = resp.content
                                cp.response.headers["Content-Type"] = magic.from_buffer(b)
                                return b
                            f = resp.raw
                            # f = ForwardedRequest(resp, 98304)
                            return cp.lib.file_generator(f, 65536)
            return cp.lib.static.serve_file(p, content_type=mime, disposition="attachment" if download else None)
    files._cp_config = {"response.stream": True}

    # @cp.expose
    # def thumbnail(self, url):
    #     headers = fcdict(cp.request.headers)
    #     headers.pop("Remote-Addr", None)
    #     headers.pop("Host", None)
    #     headers.update(Request.header())
    #     with requests.get(url, headers=headers, stream=True) as resp:
    #         ct = resp.headers.get("Content-Type")
    #         if ct == "text/html":
    #             it = resp.iter_content(65536)
    #             s = next(it).decode("utf-8", "replace")
                
    #     s = f'<!DOCTYPE HTML><html><meta http-equiv="refresh" content="0; URL={url}"/></html>'
    #     data = resp.encode("utf-8")
    #     cp.response.headers.update(CHEADERS)
    #     cp.response.headers["Location"] = url
    #     cp.response.headers["Content-Type"] = mime
    #     cp.response.headers["Content-Length"] = len(data)
    #     cp.response.headers["ETag"] = create_etag(data)
    #     cp.response.status = int(code)
    #     return data

    @cp.expose
    def static(self, *filepath):
        if not filepath:
            if cp.request.remote_ip == "127.0.0.1":
                STATIC.clear()
                send("Webserver cache cleared.")
                return b"\xf0\x9f\x92\x9c"
            raise PermissionError
        filename = "/".join(filepath)
        data, mime = fetch_static(filename)
        cp.response.headers.update(CHEADERS)
        cp.response.headers["Content-Type"] = mime
        cp.response.headers["Content-Length"] = len(data)
        cp.response.headers["ETag"] = create_etag(data)
        return data

    @cp.expose
    def mizatlas(self, *filepath):
        filename = "/".join(filepath)
        data = None
        if filename:
            with suppress(FileNotFoundError):
                data, mime = fetch_static(f"mizatlas/{filename}")
                if filename == "static/js/main.312a0124.chunk.js":
                    data = data.replace("⟨MIZA⟩".encode("utf-8"), cp.request.base.encode("utf-8"))
        if not data:
            data, mime = fetch_static("mizatlas/index.html")
        cp.response.headers.update(CHEADERS)
        cp.response.headers["Content-Type"] = mime
        cp.response.headers["Content-Length"] = len(data)
        cp.response.headers["ETag"] = create_etag(data)
        return data

    @cp.expose
    def apidoc(self):
        apidoc = getattr(self, "api", None)
        if not apidoc:
            apidoc = fetch_static(f"apidoc.html")
            data, mime = apidoc
            data2 = data.replace("⟨MIZA⟩".encode("utf-8"), cp.request.base.split("//", 1)[-1].encode("utf-8"))
            self.api = apidoc = (data2, mime)
        data, mime = apidoc
        cp.response.headers.update(CHEADERS)
        cp.response.headers["Content-Type"] = mime
        cp.response.headers["Content-Length"] = len(data)
        cp.response.headers["ETag"] = create_etag(data)
        return data

    @cp.expose
    def models(self, *filepath):
        filename = "/".join(filepath)
        data, mime = fetch_static(f"waifu2x/models/{filename}")
        cp.response.headers.update(CHEADERS)
        cp.response.headers["Content-Type"] = mime
        cp.response.headers["Content-Length"] = len(data)
        cp.response.headers["ETag"] = create_etag(data)
        return data

    @cp.expose
    def w2wbinit(self):
        data, mime = fetch_static("waifu2x/w2wbinit.png")
        cp.response.headers.update(CHEADERS)
        cp.response.headers["Content-Type"] = mime
        cp.response.headers["Content-Length"] = len(data)
        cp.response.headers["ETag"] = create_etag(data)
        return data

    @cp.expose
    def waifu2x(self, *filepath, source=None):
        if filepath:
            filename = "/".join(filepath)
            if not source:
                source = "https://gitlab.com/20kdc/waifu2x-upconv7-webgl/-/raw/master/w2wbinit.png"
            if not is_url(source):
                raise FileNotFoundError
            if not regexp("https:\\/\\/images-ext-[0-9]+\\.discordapp\\.net\\/external\\/").match(source) and not source.startswith("https://media.discordapp.net/"):
                if not source.startswith(cp.request.base):
                    t = ts_us()
                    while t in RESPONSES:
                        t += 1
                    RESPONSES[t] = fut = concurrent.futures.Future()
                    send(f"!{t}\x7fbot.data.exec.proxy({repr(source)})", escape=False)
                    j, after = fut.result()
                    RESPONSES.pop(t, None)
                    source = j["result"]
            data, mime = fetch_static("waifu2x/main.js")
            srcline = f'currentImage.src = "{source}";\n    currentImage.crossOrigin = "";'
            data = data.replace(b'currentImage.src = "w2wbinit.png";', srcline.encode("utf-8", "replace"))
            cp.response.headers.update(CHEADERS)
            cp.response.headers["Content-Type"] = mime
            cp.response.headers["Content-Length"] = len(data)
            cp.response.headers["ETag"] = create_etag(data)
            return data
        if source:
            data = f"""<!DOCTYPE html>
<html>
    <meta property="og:image" content="{source}">""" + """
    <style>
        .center {
            margin: 0;
            position: absolute;
            top: 50%;
            left: 50%;
            -ms-transform: translate(-50%, -50%);
            transform: translate(-50%, -50%);
            color: white;
        }
    </style>""" + f"""
	<body style="background-color: black;">
        <div class="center">
            <input hidden type="file" id="imageIn" accept="image/png, image/jpeg"/>
            <select hidden id="modelName">
                <option value="models/upconv_7/art/scale2.0x_model">Waifu2x Upconv7 Art</option>
            </select>
            <button hidden id="runButton">Run</button>
            <button hidden id="cancelButton">Cancel</button>
            <p hidden id="statusDiv">JS not loaded yet...</p>
            <canvas id="canvas"></canvas>
            <script src="{cp.url()}/main.js?source={urllib.parse.quote(source)}"></script>
        </div>
	</body>
</html>"""
        else:
            data = """<!DOCTYPE html>
<html>
    <style>
        .center {
            margin: 0;
            position: absolute;
            top: 50%;
            left: 50%;
            -ms-transform: translate(-50%, -50%);
            transform: translate(-50%, -50%);
            color: white;
        }
    </style>""" + f"""
	<body style="background-color: black;">
        <div class="center">
            <p>Open file</p>
            <input type="file" id="imageIn" accept="image/png, image/jpeg"/>
            <p>Select model</p>
            <select id="modelName">
                <option value="models/upconv_7/art/scale2.0x_model">Waifu2x Upconv7 Art</option>
                <option value="models/upconv_7/art/noise0_scale2.0x_model">Waifu2x Upconv7 Art (noise0)</option>
                <option value="models/upconv_7/art/noise1_scale2.0x_model">Waifu2x Upconv7 Art (noise1)</option>
                <option value="models/upconv_7/art/noise2_scale2.0x_model">Waifu2x Upconv7 Art (noise2)</option>
                <option value="models/upconv_7/art/noise3_scale2.0x_model">Waifu2x Upconv7 Art (noise3)</option>
                <option value="models/upconv_7/art/scale2.0x_model">Waifu2x Upconv7 Photo</option>
                <option value="models/upconv_7/art/noise0_scale2.0x_model">Waifu2x Upconv7 Photo (noise0)</option>
                <option value="models/upconv_7/art/noise1_scale2.0x_model">Waifu2x Upconv7 Photo (noise1)</option>
                <option value="models/upconv_7/art/noise2_scale2.0x_model">Waifu2x Upconv7 Photo (noise2)</option>
                <option value="models/upconv_7/art/noise3_scale2.0x_model">Waifu2x Upconv7 Photo (noise3)</option>
            </select>
            <p>Model data from <a href="https://github.com/nagadomi/waifu2x/">nagadomi waifu2x</a></p>
            <button id="runButton">Run</button>
            <button id="cancelButton">Cancel</button>
            <p id="statusDiv">JS not loaded yet...</p>
            <p>experimental. exposure to high amounts of data may result in hazardous levels of memory usage, which may result in system OOM.</p>
            <p>View</p>
            <canvas id="canvas"></canvas>
            <script src="{cp.url()}/main.js"></script>
        </div>
	</body>
</html>"""
        cp.response.headers.update(CHEADERS)
        cp.response.headers["Content-Type"] = mime
        cp.response.headers["Content-Length"] = len(data)
        cp.response.headers["ETag"] = create_etag(data)
        return data

    @cp.expose
    def ytdl(self, **kwargs):
        d = kwargs.get("d") or kwargs.get("download")
        v = d or kwargs.get("v") or kwargs.get("view")
        q = d or v or kwargs.get("q") or kwargs.get("query") or kwargs.get("s") or kwargs.get("search")
        if not q:
            raise EOFError
        t = ts_us()
        while t in RESPONSES:
            t += 1
        if v:
            fmt = kwargs.get("fmt")
            if not fmt:
                fmt = "opus" if d else "mp3"
            if fmt not in ("mp3", "opus", "ogg", "wav"):
                raise TypeError
            fmt = "." + fmt
            RESPONSES[t] = fut = concurrent.futures.Future()
            send(f"!{t}\x7fbot.audio.returns[{t}]=VOICE.ytdl.search({repr(q)})[0]", escape=False)
            fut.result()
            RESPONSES[t] = fut = concurrent.futures.Future()
            send(f"!{t}\x7fVOICE.ytdl.get_stream(bot.audio.returns[{t}],force=True,download=False)", escape=False)
            fut.result()
            RESPONSES[t] = fut = concurrent.futures.Future()
            send(f"!{t}\x7f(bot.audio.returns[{t}].get('name'),bot.audio.returns[{t}].get('url'))", escape=False)
            j, after = fut.result()
            name, url = j["result"]
            if not name or not url:
                raise FileNotFoundError
            h = shash(url)
            fn = "~" + h + fmt
            RESPONSES[t] = fut = concurrent.futures.Future()
            send(f"!{t}\x7fbot.audio.returns[{t}]=VOICE.ytdl.get_stream(bot.audio.returns[{t}],download={repr(fmt)})", escape=False)
            fut.result()
            RESPONSES.pop(t, None)
            fni = "cache/" + fn

            def af():
                if not os.path.exists(fni):
                    return
                if not os.path.getsize(fni):
                    return
                RESPONSES[t] = fut = concurrent.futures.Future()
                try:
                    send(f"!{t}\x7fbool(getattr(bot.audio.returns[{t}], 'loaded', None))", escape=False)
                    j, after = fut.result()
                    RESPONSES.pop(t, None)
                except:
                    print_exc()
                    RESPONSES.pop(t, None)
                    return True
                return j["result"] is not False

            f = DownloadingFile(fni, af=af)
            cp.response.headers["Accept-Ranges"] = "bytes"
            cp.response.headers.update(CHEADERS)
            cp.response.headers["Content-Disposition"] = "attachment; " * bool(d) + "filename=" + name + fmt
            if af():
                count = 1048576
                cp.response.headers["Content-Length"] = os.path.getsize(fni)
            else:
                if d:
                    cp.response.status = 202
                count = 65536
            cp.response.headers["Content-Type"] = f"audio/{fmt[1:]}"
            return cp.lib.file_generator(f, count)
        else:
            RESPONSES[t] = fut = concurrent.futures.Future()
            send(f"!{t}\x7f[VOICE.copy_entry(e) for e in VOICE.ytdl.search({repr(q)})]", escape=False)
            j, after = fut.result()
            RESPONSES.pop(t, None)
            res = j["result"]
        cp.response.headers.update(CHEADERS)
        cp.response.headers["Content-Type"] = "application/json"
        return json.dumps(res).encode("utf-8")
    ytdl._cp_config = {"response.stream": True}

    @cp.expose
    def index(self, *args, **kwargs):
        data, mime = fetch_static("index.html")
        cp.response.headers.update(CHEADERS)
        cp.response.headers["Content-Type"] = mime
        cp.response.headers["Content-Length"] = len(data)
        cp.response.headers["ETag"] = create_etag(data)
        return data

    @cp.expose
    def favicon(self, *args, **kwargs):
        data, mime = fetch_static("icon.ico")
        cp.response.headers.update(CHEADERS)
        cp.response.headers["Content-Type"] = mime
        cp.response.headers["Content-Length"] = len(data)
        cp.response.headers["ETag"] = create_etag(data)
        return data

    ip_sem = Semaphore(1, 0, rate_limit=150)

    def get_ip_ex(self):
        with suppress(SemaphoreOverflowError):
            with self.ip_sem:
                resp = Request("https://api.ipify.org", decode=True)
                if resp:
                    self.ip = resp
                return resp

    @cp.expose
    def get_ip(self, *args, **kwargs):
        self.get_ip_ex()
        data = json.dumps(dict(
            remote=cp.request.remote.ip,
            host=getattr(self, "ip", "127.0.0.1"),
        )).encode("utf-8")
        cp.response.headers.update(SHEADERS)
        cp.response.headers["Content-Type"] = "application/json"
        cp.response.headers["Content-Length"] = len(data)
        cp.response.headers["ETag"] = create_etag(data)
        return data

    @cp.config(**{"response.timeout": 7200})
    @cp.expose
    def upload_file(self, *args, **kwargs):
        ip = cp.request.remote.ip
        files = args + tuple(kwargs.values())
        files = [file for file in files if file.filename]
        if not files:
            raise EOFError
        ts = time.time_ns() // 1000
        urls = deque()
        futs = deque()

        def copy_file(obj, fn):
            with open(fn, "wb") as f:
                shutil.copyfileobj(obj, f)

        for file in files:
            fn = file.filename
            sfn = f"cache/{IND}{ts}~{fn}"
            futs.append(create_future_ex(copy_file, file.file, sfn))
            b = ts.bit_length() + 7 >> 3
            href = f"/view/" + as_str(base64.urlsafe_b64encode(ts.to_bytes(b, "big"))).rstrip("=")
            url = HOST + href
            data = (href, url, sfn)
            urls.append(data)
            send(ip + "\t" + fn + "\t" + str(data))
            ts += 1
        s = """<!DOCTYPE html>
<html>
    <head>
        <style>
        body {
            text-align: center;
            font-family: 'Comic Sans MS';
        }
        img {
            margin-top: 32px;
            display: block;
            margin-left: auto;
            margin-right: auto;
        }
        a:link {
            color: #ffff00;
            text-decoration: none;
        }
        a:visited {
            color: #ffff00;
            text-decoration: none;
        }
        a:hover {
            color: #ff0000;
            text-decoration: underline;
        }
        a:active {
            color: #00ff00;
            text-decoration: underline;
        }
        </style>
    </head>
    <body style="background-color:black;">
        <h1 style="color:white;">Upload successful!</h1>"""
        for fut in futs:
            fut.result()
        s += f"""
        <p style="color:#00ffff;">Total file size: {byte_scale(sum(os.path.getsize(f[2]) for f in urls))}B</p>
        <p style="color:#bf7fff;">Estimated file lifetime: 2 months</p>"""
        for fi in urls:
            s += f'\n<a href="{fi[0]}">{fi[1]}<br></a>'
        preview = deque()
        for f in urls:
            mime = get_mime(f[2])
            if mime.startswith("image/"):
                preview.append(f'<img width="480" src="{f[0].replace("/view/", "/preview/")}" alt="{f[2].split("~", 1)[-1]}">')
            elif mime.startswith("audio/"):
                preview.append(f'<div align="center"><audio controls><source src="{f[0]}" type="{mime}"></audio></div>')
            elif mime.startswith("video/"):
                preview.append(f'<div align="center"><video width="480" controls><source src="{f[0]}" type="{mime}"></video></div>')
            elif mime.startswith("text/"):
                preview.append(f'<a href="{fi[0].replace("/view/", "/files/")}">{fi[1].replace("/view/", "/files/")}</a>')
            else:
                preview.append(f'<a href="{fi[0].replace("/view/", "/download/")}">{fi[1].replace("/view/", "/files/")}</a>')
        if not preview:
            preview.append(f'<img src="{cp.request.base}/static/hug.gif" alt="Miza-Dottie-Hug" style="width:14.2857%;height:14.2857%;">')
        s += "\n" + "\n".join(preview)
        s += """
        <p><a href="/upload">Click here to upload another file!</a></p>
    </body>
</html>"""
        return s

    @cp.expose
    def upload(self):
        global est_last
        ip = cp.request.remote.ip
        colour = hex(colour2raw(hue2colour(xrand(1536))))[2:].upper()
        if utc() - est_last > 1800:
            est_last = utc()
            create_future_ex(estimate_life)
# Code adapted from https://github.com/mailopl/html5-xhr2-chunked-file-upload-slice
        data = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Files</title>
    <meta content="Files" property="og:title">
    <meta content="Upload a file here!" property="og:description">
    <meta content="{cp.url()}" property="og:url">
    <meta property="og:image" content="https://github.com/thomas-xin/Miza/raw/e62dfccef0cce3b0fc3b8a09fb3ca3edfedd8ab0/misc/sky-rainbow.gif">
    <meta content="#BF7FFF" data-react-helmet="true" name="theme-color">
    <link href="https://unpkg.com/boxicons@2.0.7/css/boxicons.min.css" rel="stylesheet">
</head>""" + """
<script type="text/javascript">
const BYTES_PER_CHUNK = 2097152; // 2MB chunk sizes.
var slices; // slices, value that gets decremented
var slicesTotal; // total amount of slices, constant once calculated

/**
 * Calculates slices and indirectly uploads a chunk of a file via uploadFile()
**/
function sendRequest() {
    var xhr;
    var blob = document.getElementById('fileToUpload').files[0];

    var start = 0;
    var end;
    var index = 0;

    // calculate the number of slices 
    slices = Math.ceil(blob.size / BYTES_PER_CHUNK);
    slicesTotal = slices;

    while(start < blob.size) {
        end = start + BYTES_PER_CHUNK;
        if(end > blob.size) {
            end = blob.size;
        }

        uploadFile(blob, index, start, end);

        start = end;
        index++;
    }
}

/**
 * Blob to ArrayBuffer (needed ex. on Android 4.0.4)
**/
var str2ab_blobreader = function(str, callback) {
    var blob;
    BlobBuilder = window.MozBlobBuilder || window.WebKitBlobBuilder || window.BlobBuilder;
    if (typeof(BlobBuilder) !== 'undefined') {
      var bb = new BlobBuilder();
      bb.append(str);
      blob = bb.getBlob();
    } else {
      blob = new Blob([str]);
    }
    var f = new FileReader();
    f.onload = function(e) {
        callback(e.target.result)
    }
    f.readAsArrayBuffer(blob);
}
/**
 * Performs actual upload, adjustes progress bars
 *
 * @param blob
 * @param index
 * @param start
 * @param end
 */
function uploadFile(blob, index, start, end) {
    var xhr;
    var end;
    var chunk;

    xhr = new XMLHttpRequest();

    xhr.onreadystatechange = function() {
        if(xhr.readyState == 4) {
            if(xhr.responseText) {
                alert(xhr.responseText);
            }

            slices--;

            // if we have finished all slices
            if(slices == 0) {
                mergeFile(blob);
                progressBar.max = progressBar.value = 100;
				percentageDiv.innerHTML = "100%";
            }
        }
    };

    if (blob.webkitSlice) {
        chunk = blob.webkitSlice(start, end);
    } else if (blob.mozSlice) {
        chunk = blob.mozSlice(start, end);
    } else {
		chunk = blob.slice(start, end); 
    }

    xhr.addEventListener("load",  function (evt) {
    	var percentageDiv = document.getElementById("percent");
		var progressBar = document.getElementById("progressBar");
    }, false);

	xhr.upload.addEventListener("progress", function (evt) {
		var percentageDiv = document.getElementById("percent");  
		var progressBar = document.getElementById("progressBar");

		if (evt.lengthComputable) {
            progressBar.max = slicesTotal;
            progressBar.value = index;
            percentageDiv.innerHTML = Math.round(index/slicesTotal * 10000) / 100 + "%";
		} 
	}, false);


    xhr.open("post", "upload_chunk", true);
    xhr.setRequestHeader("X-File-Name", blob.name);             // custom header with filename and full size
	xhr.setRequestHeader("X-File-Size", blob.size);
	xhr.setRequestHeader("X-Index", index);                     // part identifier
    
    if (blob.webkitSlice) {                                     // android default browser in version 4.0.4 has webkitSlice instead of slice()
    	var buffer = str2ab_blobreader(chunk, function(buf) {   // we cannot send a blob, because body payload will be empty
       		xhr.send(buf);                                      // thats why we send an ArrayBuffer
    	});	
    } else {
    	xhr.send(chunk);                                        // but if we support slice() everything should be ok
    }
}

/**
 *  Function executed once all of the slices has been sent, "TO MERGE THEM ALL!"
**/
function mergeFile(blob) {
    var xhr;
    var fd;

    xhr = new XMLHttpRequest();
    xhr.onreadystatechange = function() {
		if (xhr.readyState == XMLHttpRequest.DONE) {
			window.location.replace(xhr.responseText);
		}
	}

    fd = new FormData();
    fd.append("name", blob.name);
    fd.append("index", slicesTotal);

    xhr.open("POST", "merge", true);
    xhr.send(fd);
}
</script>

<style>
    body {
        font-family: 'Comic Sans MS';
    }
    .select {
        vertical-align: center;
        background: transparent;
        color: white;
        width: 100%;
        height: 100%;
        font-weight: 400;
        align-items: center;
    }
    .center {
        margin: 0;
        position: absolute;
        top: 50%;
        left: 50%;
        -ms-transform: translate(-50%, -50%);
        transform: translate(-50%, -50%);
    }
    a:link {
        color: #ffff00;
        text-decoration: none;
    }
    a:visited {
        color: #ffff00;
        text-decoration: none;
    }
    a:hover {
        color: #ff0000;
        text-decoration: underline;
    }
    a:active {
        color: #00ff00;
        text-decoration: underline;
    }
    """ + f"""
</style>
<body>
    <video playsinline autoplay muted loop poster="https://cdn.discordapp.com/attachments/691915140198826005/846945647873490944/GpAy.webp" style="position:fixed;right:0;bottom:0;min-width:100%;min-height:100%;z-index:-1;">
        <source src="https://cdn.discordapp.com/attachments/691915140198826005/846587863797203004/GpAy.mp4" type="video/mp4">
    </video>
    <link href="/static/hamburger.css" rel="stylesheet">
    <div class="hamburger">
        <input
            type="checkbox"
            title="Toggle menu"
        />
        <div class="items select">
            <a href="/" data-popup="Home">
                <video playsinline autoplay muted loop width="36" height="36" style="z-index:-1;">
                    <source src="https://cdn.discordapp.com/attachments/691915140198826005/846592940075515904/miza_by_smudgedpasta_de1q8lu-pre.jpgtokeneyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1cm46YXBwOj.mp4" type="video/mp4">
                </video>
            </a>
            <a href="/mizatlas" data-popup="Command Atlas">
                <video playsinline autoplay muted loop width="36" height="36" style="z-index:-1;">
                    <source src="https://cdn.discordapp.com/attachments/691915140198826005/846593904635281408/miza_has_a_leaf_blower_by_smudgedpasta_de6t2dl-pre.jpgtokeneyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJz.mp4" type="video/mp4">
                </video>
            </a>
            <a href="/upload" data-popup="File Host">
                <video playsinline autoplay muted loop width="36" height="36" style="z-index:-1;">
                    <source src="https://cdn.discordapp.com/attachments/691915140198826005/846593561444745226/magical_babey_mode_by_smudgedpasta_de1q8ky-pre.jpgtokeneyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIi.mp4" type="video/mp4">
                </video>
            </a>
            <a href="/apidoc" data-popup="API Documentation">
                <video playsinline autoplay muted loop width="36" height="36" style="z-index:-1;">
                    <source src="https://cdn.discordapp.com/attachments/691915140198826005/846590061901381632/deahc7l-a9773147-259d-4226-b0b6-195c6eb1f3c0.pngtokeneyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOi.mp4" type="video/mp4">
                </video>
            </a>
            <a 
                href="/time"
                data-popup="Clock"
                class='bx bx-time'></a>
        </div>
        <div class="hambg"></div>
    </div>
    <div class="center">
		<div id="percent" align="center" style="color:white;">
            <h1>Upload a file here!</h1>
            <a href="/redirect">Click here to shorten or proxy a URL!</a>
        </div><br>
		<input style="color:white;" type="file" name="file" id="fileToUpload">
		<button onclick="sendRequest()">Upload</button><br>
		<div align="center"><progress id="progressBar" value="0" max="100"></progress></div>
	</div>
</body>
</html>"""
        cp.response.headers.update(CHEADERS)
        cp.response.headers["Content-Type"] = "text/html"
        cp.response.headers["Content-Length"] = len(data)
        cp.response.headers["ETag"] = create_etag(data)
        return data

    @cp.expose
    def upload_chunk(self, **kwargs):
        s = cp.request.remote.ip + "%" + cp.request.headers.get("x-file-name", "")
        h = hash(s) % 2 ** 48
        fn = f"cache/{h}%" + cp.request.headers.get("x-index", "0")
        with open(fn, "wb") as f:
            shutil.copyfileobj(cp.request.body.fp, f)

    @cp.expose
    @cp.tools.accept(media="multipart/form-data")
    def merge(self, **kwargs):
        ts = time.time_ns() // 1000
        name = kwargs.get("name", "")
        s = cp.request.remote.ip + "%" + name
        h = hash(s) % 2 ** 48
        n = f"cache/{h}%"
        fn = f"cache/{IND}{ts}~" + name
        high = int(kwargs.get("index", "0"))
        os.rename(n + "0", fn)
        if high > 1:
            with open(fn, "ab") as f:
                for i in range(1, high):
                    gn = n + str(i)
                    with open(gn, "rb") as g:
                        shutil.copyfileobj(g, f)
                    os.remove(gn)
        b = ts.bit_length() + 7 >> 3
        return "/p/" + as_str(base64.urlsafe_b64encode(ts.to_bytes(b, "big"))).rstrip("=")

    @cp.expose
    def upload_url(self, **kwargs):
        ts = time.time_ns() // 1000
        url = kwargs["url"]
        fn = f"../cache/{IND}{ts}~" + url.rsplit("/", 1)[-1].split("?", 1)[0].rsplit(".", 1)[0]
        subprocess.run([sys.executable, "downloader.py", url, fn], stdout=subprocess.DEVNULL, cwd="misc")
        b = ts.bit_length() + 7 >> 3
        return HOST + "/p/" + as_str(base64.urlsafe_b64encode(ts.to_bytes(b, "big"))).rstrip("=")

    @cp.expose(("proxy",))
    def redirect(self):
        data = """<!doctype HTML><html>
<link href="https://unpkg.com/boxicons@2.0.7/css/boxicons.min.css" rel="stylesheet">
<style>
body {
	font-family: 'Rockwell';
	color: #00ffff;
	background: black;
}
.center {
	margin: 0;
	position: absolute;
	top: 50%;
	left: 50%;
	-ms-transform: translate(-50%, -50%);
	transform: translate(-50%, -50%);
}
.tooltip {
  position: relative;
  display: inline-block;
  border-bottom: 1px dotted black;
}
.tooltip .tooltiptext {
  visibility: hidden;
  width: 120px;
  background-color: rgba(0, 0, 0, 0.5);
  color: #fff;
  text-align: center;
  border-radius: 6px;
  padding: 5px 0;
  position: absolute;
  z-index: 1;
}
.tooltip:hover .tooltiptext {
  visibility: visible;
}
</style>
<body>
	<video playsinline autoplay muted loop poster="https://cdn.discordapp.com/attachments/691915140198826005/846945647873490944/GpAy.webp" style="position:fixed;right:0;bottom:0;min-width:100%;min-height:100%;z-index:-1;">
        <source src="https://cdn.discordapp.com/attachments/691915140198826005/846587863797203004/GpAy.mp4" type="video/mp4">
    </video>
    <link href="/static/hamburger.css" rel="stylesheet">
    <div class="hamburger">
        <input
            type="checkbox"
            title="Toggle menu"
        />
        <div class="items select">
            <a href="/" data-popup="Home">
                <video playsinline autoplay muted loop width="36" height="36" style="z-index:-1;">
                    <source src="https://cdn.discordapp.com/attachments/691915140198826005/846592940075515904/miza_by_smudgedpasta_de1q8lu-pre.jpgtokeneyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1cm46YXBwOj.mp4" type="video/mp4">
                </video>
            </a>
            <a href="/mizatlas" data-popup="Command Atlas">
                <video playsinline autoplay muted loop width="36" height="36" style="z-index:-1;">
                    <source src="https://cdn.discordapp.com/attachments/691915140198826005/846593904635281408/miza_has_a_leaf_blower_by_smudgedpasta_de6t2dl-pre.jpgtokeneyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJz.mp4" type="video/mp4">
                </video>
            </a>
            <a href="/upload" data-popup="File Host">
                <video playsinline autoplay muted loop width="36" height="36" style="z-index:-1;">
                    <source src="https://cdn.discordapp.com/attachments/691915140198826005/846593561444745226/magical_babey_mode_by_smudgedpasta_de1q8ky-pre.jpgtokeneyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIi.mp4" type="video/mp4">
                </video>
            </a>
            <a href="/apidoc" data-popup="API Documentation">
                <video playsinline autoplay muted loop width="36" height="36" style="z-index:-1;">
                    <source src="https://cdn.discordapp.com/attachments/691915140198826005/846590061901381632/deahc7l-a9773147-259d-4226-b0b6-195c6eb1f3c0.pngtokeneyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOi.mp4" type="video/mp4">
                </video>
            </a>
            <a 
                href="/time"
                data-popup="Clock"
                class='bx bx-time'></a>
        </div>
        <div class="hambg"></div>
    </div>
	<div class="center">
		<h1 style="color: white;">Create a redirect or proxy URL here!</h1>
		<form action="" method="get" class="form-example">
			<h2>URL</h2>
			<div class="tooltip">
				<input type=url name="url" style="width:240;"/>
				<span class="tooltiptext"> The URL to forward.</span>
			</div>
			<h2>Status Code</h2>
			<div class="tooltip">
				<input type=number name="code" value="307" min="100" max="599"/>
				<span class="tooltiptext"> The status code returned by the response. Should be one of {301, 302, 303, 307, 308} for a redirect.</span>
			</div>
			<h2>Type</h2>
			<div class="tooltip">
				<input type=radio value="1" name="ftype" checked=true/>Redirect
				<span class="tooltiptext"> A redirect page will simply forward users to the destination.</span>
			</div>
			<div class="tooltip">
				<input type=radio value="2" name="ftype"/>Proxy
				<span class="tooltiptext"> A proxy page will forward the data from the destination to the user.</span>
			</div>
			<br><br>
			<input type=submit value="Create" formaction="/forward" formenctype="application/x-www-form-urlencoded" formmethod="post"/>
		</form>
	</div>
</body>
</html>"""
        cp.response.headers.update(CHEADERS)
        cp.response.headers["Content-Type"] = "text/html"
        cp.response.headers["Content-Length"] = len(data)
        cp.response.headers["ETag"] = create_etag(data)
        return data

    @cp.expose
    @cp.tools.accept(media="multipart/form-data")
    def forward(self, **kwargs):
        ts = time.time_ns() // 1000
        fn = f"cache/{IND}{ts}~.forward$"
        url = kwargs.get("url")
        if not url:
            raise FileNotFoundError
        code = int(kwargs.get("code", 307))
        ftype = int(kwargs.get("ftype", 1))
        s = f'<!DOCTYPE HTML><!--["{url}",{code},{ftype}]--><html><meta http-equiv="refresh" content="0; URL={url}"/></html>'
        with open(fn, "w", encoding="utf-8") as f:
            f.write(s)
        b = ts.bit_length() + 7 >> 3
        url = f"/p/" + as_str(base64.urlsafe_b64encode(ts.to_bytes(b, "big"))).rstrip("=")
        raise cp.HTTPRedirect(url, status=307)

    @cp.expose(("time", "timezones"))
    def timezone(self):
        ip = cp.request.remote.ip
        try:
            data = get_geo(ip)
            tz = data["timezone"]
            dt = datetime.datetime.now(pytz.timezone(tz))
            colour = hex(colour2raw(hue2colour(xrand(1536))))[2:].upper()
            html = """<!DOCTYPE html>
<html>
    <head>
        <meta charset="utf-8">
        <title>Timezones</title>
        <meta content="Timezones" property="og:title">
        <meta content="Find your current timezone here!" property="og:description">
        <meta content=\"""" + cp.url() + """\" property="og:url">
        <meta property="og:image" content="https://github.com/thomas-xin/Miza/raw/e62dfccef0cce3b0fc3b8a09fb3ca3edfedd8ab0/misc/sky-rainbow.gif">
        <meta content="#""" + colour + """\" data-react-helmet="true" name="theme-color">
        <meta http-equiv="refresh" content="60">
        <link rel="stylesheet" type="text/css" href="/static/timezonestyles.css">
        <link href="https://unpkg.com/boxicons@2.0.7/css/boxicons.min.css" rel="stylesheet">
    </head>
    <body>""" + f"""
        <link href="/static/hamburger.css" rel="stylesheet">
        <div class="hamburger">
            <input
                type="checkbox"
                title="Toggle menu"
            />
            <div class="items select">
                <a href="/" data-popup="Home">
                    <video playsinline autoplay muted loop width="36" height="36" style="z-index:-1;">
                        <source src="https://cdn.discordapp.com/attachments/691915140198826005/846592940075515904/miza_by_smudgedpasta_de1q8lu-pre.jpgtokeneyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1cm46YXBwOj.mp4" type="video/mp4">
                    </video>
                </a>
                <a href="/mizatlas" data-popup="Command Atlas">
                    <video playsinline autoplay muted loop width="36" height="36" style="z-index:-1;">
                        <source src="https://cdn.discordapp.com/attachments/691915140198826005/846593904635281408/miza_has_a_leaf_blower_by_smudgedpasta_de6t2dl-pre.jpgtokeneyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJz.mp4" type="video/mp4">
                    </video>
                </a>
                <a href="/upload" data-popup="File Host">
                    <video playsinline autoplay muted loop width="36" height="36" style="z-index:-1;">
                        <source src="https://cdn.discordapp.com/attachments/691915140198826005/846593561444745226/magical_babey_mode_by_smudgedpasta_de1q8ky-pre.jpgtokeneyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIi.mp4" type="video/mp4">
                    </video>
                </a>
                <a href="/apidoc" data-popup="API Documentation">
                    <video playsinline autoplay muted loop width="36" height="36" style="z-index:-1;">
                        <source src="https://cdn.discordapp.com/attachments/691915140198826005/846590061901381632/deahc7l-a9773147-259d-4226-b0b6-195c6eb1f3c0.pngtokeneyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOi.mp4" type="video/mp4">
                    </video>
                </a>
                <a 
                    href="/time"
                    data-popup="Clock"
                    class='bx bx-time'></a>
            </div>
            <div class="hambg"></div>
        </div>
        <div class="main">
            <h3>Estimated time:</h3>
            <h1>""" + str(dt) + """</h1>
            <h2>Detected timezone: """ + tz + f"""</h2>
            <p class="align_left">
                <a class="glow" href="/time">Refresh</a>
            </p>
            <p class="align_right">
                <a class="glow" href="/">Home</a>
            </p>
        </div>
        <video playsinline autoplay muted loop class="border" style="width:14.2857%;height:14.2857%;">
            <source src="https://cdn.discordapp.com/attachments/691915140198826005/846593561444745226/magical_babey_mode_by_smudgedpasta_de1q8ky-pre.jpgtokeneyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIi.mp4" type="video/mp4">
        </video>
    </body>
</html>"""
            return html
        except:
            send(traceback.format_exc())
            raise

    @cp.expose
    def backup(self, token="~"):
        at = AUTH.get("discord_token")
        if token != at:
            if cp.url(base="").strip("/") != at:
                raise InterruptedError
        t = ts_us()
        while t in RESPONSES:
            t += 1
        RESPONSES[t] = fut = concurrent.futures.Future()
        send(f"!{t}\x7fbot.backup()", escape=False)
        j, after = fut.result()
        RESPONSES.pop(t, None)
        cp.response.headers.update(CHEADERS)
        return cp.lib.static.serve_file(os.getcwd() + "/" + j["result"], content_type="application/zip", disposition="attachment")
    backup._cp_config = {"response.stream": True}

    @cp.expose(("eval", "exec"))
    def execute(self, token, *args, **kwargs):
        if token != AUTH.get("discord_token"):
            raise InterruptedError
        url = cp.url(base="", qs=cp.request.query_string)
        content = urllib.parse.unquote(url.split("?", 1)[0].lstrip("/").split("/", 2)[-1])
        t = ts_us()
        while t in RESPONSES:
            t += 1
        RESPONSES[t] = fut = concurrent.futures.Future()
        send(f"!{t}\x7f{content}", escape=False)
        j, after = fut.result()
        RESPONSES.pop(t, None)
        return json.dumps(j["result"])

    @cp.expose
    def eval2(self, token, *args, **kwargs):
        if token != AUTH.get("discord_token"):
            raise InterruptedError
        url = cp.url(base="", qs=cp.request.query_string)
        content = urllib.parse.unquote(url.split("?", 1)[0].lstrip("/").split("/", 2)[-1])
        return str(eval(content, globals())).encode("utf-8")

    try:
        with open("saves/mpdata.json", "rb") as f:
            mpdata = json.load(f)
    except FileNotFoundError:
        mpdata = {}
    except:
        if os.path.exists("saves/mpdata\x7f\x7f.json"):
            with open("saves/mpdata\x7f\x7f.json", "rb") as f:
                mpdata = json.load(f)
        else:
            mpdata = {}
            print_exc()
    mpdata_updated = False

    try:
        with open("saves/mpact.json", "rb") as f:
            mpact = pickle.load(f)
    except FileNotFoundError:
        mpact = {}
    except:
        if os.path.exists("saves/mpact\x7f\x7f.json"):
            with open("saves/mpact\x7f\x7f.json", "rb") as f:
                mpact = pickle.load(f)
        else:
            mpact = {}
            print_exc()

    mpresponse = {}

    @cp.expose
    def mphb(self, playing=None):
        mpdata = self.mpdata
        ip = cp.request.remote.ip
        t = utc()
        try:
            if playing is None or cp.request.method.casefold() != "patch" or cp.request.headers["User-Agent"] != "Miza Player":
                raise KeyError
        except KeyError:
            if ip in mpdata:
                d = t - mpdata[ip][1]
                if d < 60:
                    mpdata[ip][0] += d
                mpdata[ip][1] = min(mpdata[ip][1], t - 60)
                d = t - mpdata[ip][3]
                if d < 60:
                    mpdata[ip][2] += d
                mpdata[ip][3] = min(mpdata[ip][3], t - 60)
            cp.response.status = 450
            return ""
        if ip not in mpdata:
            mpdata[ip] = [0,] * 4
        d = t - mpdata[ip][1]
        if d < 60:
            mpdata[ip][0] += d
        mpdata[ip][1] = t
        if full_prune(playing) == "true":
            d = t - mpdata[ip][3]
            if d < 60:
                mpdata[ip][2] += d
            mpdata[ip][3] = t
        else:
            d = t - mpdata[ip][3]
            if d < 60:
                mpdata[ip][2] += d
            mpdata[ip][3] = min(mpdata[ip][3], t - 60)
        if not self.mpdata_updated:
            self.mpdata_updated = True
            create_future_ex(self.mpdata_update)
        try:
            resp = self.mpresponse.pop(ip)
        except KeyError:
            try:
                resp = self.mpresponse[None]
            except KeyError:
                return "💜"
        return "".join(chr(xrand(32, 127)) + chr(xrand(48, 96)) + c for c in resp.replace("$$$", "\n")[::-1])

    mpimg = {}

    @cp.expose
    def mpinsights(self):
        values = self.mpget()
        for i in range(3):
            values[i] = int(values[i])
        if "text/html" not in cp.request.headers.get("Accept", ""):
            self.ensure_mpins()
            histories = [None] * len(values)
            hours = histories.copy()
            for k in range(len(histories)):
                width = np.clip(len(self.ins_data[k]), 3, 96)
                histories[k] = list(supersample(self.ins_data[k], width))
                hours[k] = len(self.ins_data[k])
            return json.dumps(dict(
                current=dict(
                    live_users=values[2],
                    active_users=values[1],
                    total_users=values[0],
                    total_playtime=values[4],
                    total_use_time=values[3],
                    average_playtime=values[5],
                ),
                historical=dict(
                    live_users=[histories[2], hours[2]],
                    active_users=[histories[1], hours[2]],
                    total_users=[histories[0], hours[2]],
                    total_playtime=[histories[4], hours[2]],
                    total_use_time=[histories[3], hours[2]],
                    average_playtime=[histories[5], hours[2]],
                ),
            )).encode("utf-8")
        create_future_ex(self.ensure_mpins)
        return """<!DOCTYPE html><html>
<head>
    <meta charset="utf-8">
    <title>Insights</title>
    <meta content="Miza Player Insights" property="og:title">
    <meta content="See the activity history for the Miza Player program!" property="og:description">
    <meta content="{cp.url()}" property="og:url">
    <meta property="og:image" content="https://github.com/thomas-xin/Miza/raw/e62dfccef0cce3b0fc3b8a09fb3ca3edfedd8ab0/misc/sky-rainbow.gif">
    <meta content="#BF7FFF" data-react-helmet="true" name="theme-color">
    <style>
        body {
            font-family:Rockwell;
            background:black;
            color:#bfbfbf;
            text-align:center;
        }
        .center {
            display: block;
            margin-left: auto;
            margin-right: auto;
            max-width: 100%;
        }
    </style>
</head>""" + f"""
<body>
    <h1 style="color:white;">Miza Player Insights</h1>
    Live users: {values[2]}
    <img class="center" src="http://i.mizabot.xyz/mpins/2">
    Active users: {values[1]}
    <img class="center" src="http://i.mizabot.xyz/mpins/1">
    Total users: {values[0]}
    <img class="center" src="http://i.mizabot.xyz/mpins/0">
    <br>
    Total playtime: {sec2time(values[4])}
    <img class="center" src="http://i.mizabot.xyz/mpins/4">
    Total use time: {sec2time(values[3])}
    <img class="center" src="http://i.mizabot.xyz/mpins/3">
    Average playtime per user: {sec2time(values[5])}
    <img class="center" src="http://i.mizabot.xyz/mpins/5">
</body>
</html>"""

    def ensure_mpins(self):
        try:
            ins_time = getattr(self, "ins_time", 0)
            t = utc()
            if t - ins_time >= 30:
                self.mpimg.clear()
                self.ins_wait = concurrent.futures.Future()
                k = self.mpact.keys()
                data = [deque() for i in range(len(next(reversed(self.mpact.values()))))]
                for i in range(min(k), max(k) + 1):
                    values = self.mpact.get(i) or values
                    for j, v in enumerate(values):
                        data[j].append(v)
                self.ins_data = data
                self.ins_time = t
                self.ins_wait.set_result(None)
                self.ins_wait = None
        except:
            send(traceback.format_exc())

    @cp.config(**{"response.timeout": 7200})
    @cp.expose
    def mpins(self, k):
        k = int(k)
        try:
            fn = self.mpimg[k]
        except KeyError:
            pass
        else:
            if os.path.exists(fn) and utc() - os.path.getmtime(fn) < 20:
                return cp.lib.static.serve_file(fn, content_type="image/png")
        while self.ins_wait:
            self.ins_wait.result()
        width = np.clip(len(self.ins_data[k]), 3, 960)
        arr = list(supersample(self.ins_data[k], width))

        t = ts_us()
        while t in RESPONSES:
            t += 1
        RESPONSES[t] = fut = concurrent.futures.Future()
        arr_repr = "pickle.loads(" + repr(pickle.dumps(arr)) + ")"
        hours = len(self.ins_data[k])
        content = f'await process_image("plt_mp", "$", ({arr_repr}, {hours}, {k}))'
        send(f"!{t}\x7f{content}", escape=False)
        j, after = fut.result()
        RESPONSES.pop(t, None)
        self.mpimg[k] = fn = os.path.abspath(f"misc/{k}.png")
        return cp.lib.static.serve_file(fn, content_type="image/png")


    # names = ("total_users", "active_users", "live_users", "active_seconds", "live_seconds", "seconds_per_user")
    def mpget(self):
        mpdata = self.mpdata
        values = [len(mpdata), 0, 0, 0, 0, 0]
        t = utc()
        for active, atime, listen, ltime in mpdata.values():
            values[1] += t - atime < 60
            values[2] += t - ltime < 60
            values[3] += active
            values[4] += listen
        values[5] = values[4] / values[0]
        return values

    def mpdata_update(self):
        try:
            time.sleep(20)
            self.mpdata_updated = False
            if not os.path.exists("saves/mpdata.json"):
                with open("saves/mpdata.json", "w") as f:
                    json.dump(self.mpdata, f)
            else:
                with open("saves/mpdata\x7f.json", "w") as f:
                    json.dump(self.mpdata, f)
                if os.path.exists("saves/mpdata\x7f\x7f.json"):
                    os.remove("saves/mpdata\x7f\x7f.json")
                os.rename("saves/mpdata.json", "saves/mpdata\x7f\x7f.json")
                os.rename("saves/mpdata\x7f.json", "saves/mpdata.json")
        except:
            send(traceback.format_exc())

    def mpact_update(self):
        try:
            time.sleep(20)
            self.mpact_updated = False
            if not os.path.exists("saves/mpact.json"):
                with open("saves/mpact.json", "wb") as f:
                    pickle.dump(self.mpact, f)
            else:
                with open("saves/mpact\x7f.json", "wb") as f:
                    pickle.dump(self.mpact, f)
                if os.path.exists("saves/mpact\x7f\x7f.json"):
                    os.remove("saves/mpact\x7f\x7f.json")
                os.rename("saves/mpact.json", "saves/mpact\x7f\x7f.json")
                os.rename("saves/mpact\x7f.json", "saves/mpact.json")
        except:
            send(traceback.format_exc())

    def mp_activity(self):
        try:
            self.act_time = os.path.getmtime("saves/mpact.json") // 3600
        except FileNotFoundError:
            self.act_time = 0
        while True:
            try:
                t = int(utc() // 3600)
                if t > self.act_time:
                    self.act_time = t
                    values = self.mpget()
                    self.mpact[t] = values
                    self.mpact_update()
                    self.mpimg.clear()
            except:
                send(traceback.format_exc())
            time.sleep(60)

    @cp.expose(("commands",))
    def command(self, content="", input=""):
        ip = cp.request.remote.ip
        if ip == "127.0.0.1":
            t, after = content.split("\x7f", 1)
            t = int(t)
            after = float(after)
            cl = int(cp.request.headers["Content-Length"])
            j = json.loads(cp.request.body.read(cl))
            if t in RESPONSES:
                RESPONSES[t].set_result((j, after))
                return b"\xf0\x9f\x92\x9c"
        content = input or urllib.parse.unquote(cp.url(base="", qs=cp.request.query_string).rstrip("?").split("/", 2)[-1])
        data = get_geo(ip)
        tz = data["timezone"]
        if " " not in content:
            content += " "
        t = ts_us()
        while t in RESPONSES:
            t += 1
        RESPONSES[t] = fut = concurrent.futures.Future()
        send(f"~{t}\x7f{ip}\x7f{tz}\x7f{content}", escape=False)
        j, after = fut.result(timeout=420)
        RESPONSES.pop(t, None)
        a = after - utc()
        if a > 0:
            cp.response.headers["Retry-After"] = a
        cp.response.headers.update(HEADERS)
        return json.dumps(j)

    @cp.expose(("cat", "cats", "dog", "dogs", "neko", "nekos", "giphy"))
    def imagepool(self, tag="", refresh=60):
        name = cp.url(base="").rsplit("/", 1)[-1]
        command = name.rstrip("s")
        argv = tag
        try:
            args = smart_split(argv)
        except ValueError:
            args = argv.split()
        t = ts_us()
        while t in RESPONSES:
            t += 1
        RESPONSES[t] = fut = concurrent.futures.Future()
        send(f"!{t}\x7fbot.commands.{command}[0](bot=bot,channel=None,flags='v',args={repr(args)},argv={repr(argv)})", escape=False)
        j, after = fut.result()
        RESPONSES.pop(t, None)
        url = j["result"]
        refresh = float(refresh or 60)
        if fcdict(cp.request.headers).get("Accept") == "application/json":
            return url
        cp.response.headers.update(HEADERS)
        return f"""<!DOCTYPE html>
<html>
<head>
<meta property="og:image" content="{url}">
<meta http-equiv="refresh" content="{refresh}; URL={cp.url(qs=cp.request.query_string)}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>""" + """
img {
  display: block;
  margin-left: auto;
  margin-right: auto;
  margin-top: auto;
  margin-bottom: auto;
}
.center {
  margin: 0;
  position: absolute;
  top: 50%;
  left: 50%;
  -ms-transform: translate(-50%, -50%);
  transform: translate(-50%, -50%);
  max-width: 100%;
  max-height: 100%;        
}""" + f"""
</style>
</head>
<body style="background-color:black;">
<img src="{url}" class="center">
</body>
</html>"""

# @app.after_request
# def custom_header(response):
#     response.headers.update(HEADERS)
#     return response


def ensure_parent(proc, parent):
    while True:
        while len(RESPONSES) > 65536:
            try:
                RESPONSES.pop(next(iter(RESPONSES)))
            except:
                pass
        if not parent.is_running():
            psutil.Process().kill()
        time.sleep(6)

if __name__ == "__main__":
    pid = os.getpid()
    ppid = os.getppid()
    send(f"Webserver starting on port {PORT}, with PID {pid} and parent PID {ppid}...")
    proc = psutil.Process(pid)
    parent = psutil.Process(ppid)
    create_thread(ensure_parent, proc, parent)
    server = Server()
    create_thread(server.mp_activity)
    create_future_ex(server.get_ip)
    cp.quickstart(server, "/", config)