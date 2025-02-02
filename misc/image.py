#!/usr/bin/python3

import os, sys, io, time, concurrent.futures, subprocess, psutil, collections, traceback, re, requests, blend_modes, pdf2image, zipfile, contextlib, filetype, pyqrcode, ast, colorspace, pickle
import numpy as np
import PIL
from PIL import Image, ImageCms, ImageOps, ImageChops, ImageDraw, ImageFilter, ImageEnhance, ImageMath, ImageStat
Image.MAX_IMAGE_PIXELS = 4294967296
from zipfile import ZipFile
import matplotlib.pyplot as plt
colorlib = colorspace.colorlib()
from math import *

write, sys.stdout.write = sys.stdout.write, lambda *args, **kwargs: None
import pygame
sys.stdout.write = write

requests = requests.Session()


def as_str(s):
    if type(s) in (bytes, bytearray, memoryview):
        return bytes(s).decode("utf-8", "replace")
    return str(s)

literal_eval = lambda s: ast.literal_eval(as_str(s).lstrip())

mpf = float
deque = collections.deque
suppress = contextlib.suppress

exc = concurrent.futures.ThreadPoolExecutor(max_workers=3)

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

exc.submit(load_mimes)

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
    if not out:
        out = simple_mimes(path, mime)
    return out

class magic:
    from_file = from_file
    from_buffer = from_file

start = time.time()
CACHE = {}
ANIM = False

qr_bytes = [
    16, 28, 44, 64, 86, 108, 124, 154, 182, 216, 254, 290, 334, 365, 415, 453, 507, 563, 627,
    669, 714, 782, 860, 914, 1000, 1062, 1128, 1193, 1267, 1373, 1455, 1541, 1631, 1725, 1812, 1914, 1992, 2102, 2216, 2334,
]
qr_bytes_ex = [
    2434, 2566, 2702, 2812, 2956,
]

SWIRL = None

def to_qr(s, rainbow=False):
    global SWIRL
    if type(s) is str:
        s = s.encode("utf-8")
    size = len(s)
    err = "M" if size <= 2334 else "L"
    ver = None
    # if size > 125:
    #     if size <= 2334:
    #         for i, n in enumerate(qr_bytes):
    #             if n >= size:
    #                 ver = i + 1
    #                 break
    #     if ver is None:
    #         for i, n in enumerate(qr_bytes_ex):
    #             if n >= size:
    #                 ver = i + 36
    #                 err = "L"
    #     if ver is None:
    #         raise OverflowError("Input string too large for QR code encoding.")
    img = pyqrcode.create(s, error=err, version=ver, mode=None, encoding="utf-8" if max(s) >= 80 else "ascii")
    fn = f"cache/{time.time_ns() // 1000}.png"
    if not os.path.exists(fn):
        img.png(fn, scale=1, module_color=(255,) * 3, background=(0,) * 4)
    imo = Image.open(fn)
    im = imo.convert("1")
    imo.close()
    im = im.resize((512, 512), resample=Image.NEAREST)
    if rainbow:
        if SWIRL is None:
            imo = Image.open("misc/swirl.png")
            SWIRL = imo.resize((512, 512), resample=Image.BILINEAR)
            imo.close()
        count = 128

        def qr_iterator(image):
            filt1 = filt2 = SWIRL
            # spl = hsv_split(SWIRL, convert=False)
            spl = SWIRL.convert("HSV").split()
            for i in range(count):
                if i:
                    # hue1 = spl[0] + round(i * 256 / count)
                    # hue2 = spl[0] - round(i * 256 / count)
                    # filt1 = hsv_merge(hue1, *spl[1:])
                    # filt2 = hsv_merge(hue2, *spl[1:])
                    hue1 = spl[0].point(lambda x: round(x + 256 * i / count) & 255)
                    hue2 = spl[0].point(lambda x: round(x - 256 * i / count) & 255)
                    filt1 = Image.merge("HSV", (hue1, spl[1], spl[2])).convert("RGB")
                    filt2 = Image.merge("HSV", (hue2, spl[1], spl[2])).convert("RGB")
                filt1 = ImageEnhance.Brightness(ImageEnhance.Contrast(filt1).enhance(0.5)).enhance(2)
                filt2 = ImageChops.invert(ImageEnhance.Brightness(ImageEnhance.Contrast(filt2).enhance(0.5)).enhance(2)).transpose(Image.FLIP_LEFT_RIGHT)
                filt1.paste(filt2, mask=image)
                yield filt1

        return dict(duration=4800, count=count, frames=qr_iterator(im))
    return ImageChops.invert(im).convert("RGBA")


def logging(func):
    def call(self, *args, **kwargs):
        try:
            output = func(self, *args, **kwargs)
        except:
            print(traceback.format_exc(), end="")
            raise
        return output
    return call


# Converts a time interval represented using days:hours:minutes:seconds, to a value in seconds.
def time_parse(ts):
    data = ts.split(":")
    t = 0
    mult = 1
    while len(data):
        t += float(data[-1]) * mult
        data = data[:-1]
        if mult <= 60:
            mult *= 60
        elif mult <= 3600:
            mult *= 24
        elif len(data):
            raise TypeError("Too many time arguments.")
    return t

# URL string detector
url_match = re.compile("^(?:http|hxxp|ftp|fxp)s?:\\/\\/[^\\s<>`|\"']+$")
is_url = lambda url: url_match.search(url)
discord_match = re.compile("^https?:\\/\\/(?:[a-z]+\\.)?discord(?:app)?\\.com\\/")
is_discord_url = lambda url: discord_match.findall(url)

fcache = "cache" if os.path.exists("cache") else "../cache"

def header():
    return {
        "DNT": "1",
        "user-agent": f"Mozilla/5.{(time.time_ns() // 1000) % 10}",
    }

def get_request(url):
    if is_discord_url(url) and "attachments/" in url[:64]:
        try:
            a_id = int(url.split("?", 1)[0].rsplit("/", 2)[-2])
        except ValueError:
            pass
        else:
            fn = f"{fcache}/attachment_{a_id}.bin"
            if os.path.exists(fn):
                with open(fn, "rb") as f:
                    print(f"Attachment {a_id} loaded from cache.")
                    return f.read()
    with requests.get(url, headers=header(), stream=True, timeout=12) as resp:
        return resp.content


from_colour = lambda colour, size=128, key=None: Image.new("RGB" + "A" * (len(colour) > 3), (size, size), tuple(colour))

def from_gradient(shape, count, colour):
    mode = "RGB" + "A" * (len(colour) > 3)
    s = 960
    if shape == "linear":
        data = np.linspace(0, count, num=s, dtype=np.float32)
        if count > 1:
            data %= 1
        data = [(data * c).astype(np.uint8) for c in colour]
        spl = [fromarray(i) for i in data]
        im = Image.merge(mode, spl)
        return im.resize((s,) * 2, resample=Image.NEAREST)
    if shape == "radial":
        try:
            data = globals()["g-1"]
        except KeyError:
            data = np.linspace(-1, 1, num=s, dtype=np.float32)
            data **= 2
            data = np.array([data] * s)
            data += data.T
            data = np.sqrt(data, out=data)
            np.subtract(1, data, out=data)
            np.clip(data, 0, None, out=data)
            globals()["g-1"] = data
        if count != 1:
            data = data * count
            if count > 1:
                data %= 1
        data = [(data * c).astype(np.uint8) for c in colour]
        spl = [fromarray(i) for i in data]
        return Image.merge(mode, spl)
    if shape == "conical":
        try:
            data = globals()["g-2"]
        except KeyError:
            m = (s - 1) / 2
            row = np.arange(s, dtype=np.float32)
            row -= m
            data = [None] * s
            for i in range(s):
                data[i] = a = np.arctan2(i - m, row)
                a *= 1 / tau
            data = np.float32(data).T
            globals()["g-2"] = data
        if count != 1:
            data = data * count
            if count > 1:
                data %= 1
        data = [(data * c).astype(np.uint8) for c in colour]
        spl = [fromarray(i) for i in data]
        return Image.merge(mode, spl)
    if shape == "polygon":
        pass

def rgb_split(image, dtype=np.uint8):
    channels = None
    if "RGB" not in str(image.mode):
        if str(image.mode) == "L":
            channels = [np.asarray(image, dtype=dtype)] * 3
        else:
            image = image.convert("RGB")
    if channels is None:
        a = np.asarray(image, dtype=dtype)
        channels = np.moveaxis(a, -1, 0)[:3]
    return channels

def xyz_split(image, convert=True, dtype=np.uint8):
    out = rgb_split(image, dtype=np.float32)
    out *= 1 / 255
    for r, g, b in zip(*out):
        x, y, z = colorlib.RGB_to_XYZ(r, g, b)
        r[:] = x
        g[:] = y
        b[:] = z
    X, Y, Z = out
    X *= 255 / 96
    Y *= 255 / 100
    Z *= 255 / 109
    for c in out:
        np.round(c, out=c)
    if convert:
        out = list(fromarray(a, "L") for a in out)
    else:
        out = np.asarray(out, dtype=dtype)
    return out

def hsv_split(image, convert=True, partial=False, dtype=np.uint8):
    channels = rgb_split(image, dtype=np.uint32)
    R, G, B = channels
    m = np.min(channels, 0)
    M = np.max(channels, 0)
    C = M - m #chroma
    Cmsk = C != 0

    # Hue
    H = np.zeros(R.shape, dtype=np.float32)
    for i, colour in enumerate(channels):
        mask = (M == colour) & Cmsk
        hm = channels[i - 2][mask].astype(np.float32)
        hm -= channels[i - 1][mask]
        hm /= C[mask]
        if i:
            hm += i << 1
        H[mask] = hm
    H *= 256 / 6
    H = H.astype(dtype)

    if partial:
        return H, M, m, C, Cmsk, channels

    # Saturation
    S = np.zeros(R.shape, dtype=dtype)
    Mmsk = M != 0
    S[Mmsk] = np.clip(256 * C[Mmsk] // M[Mmsk], None, 255)

    # Value
    V = M.astype(dtype)

    out = [H, S, V]
    if convert:
        out = list(fromarray(a, "L") for a in out)
    return out

def hsl_split(image, convert=True, dtype=np.uint8):
    out = rgb_split(image, dtype=np.float32)
    out *= 1 / 255
    for r, g, b in zip(*out):
        h, l, s = colorlib.RGB_to_HLS(r, g, b)
        r[:] = h
        g[:] = s
        b[:] = l
    H, L, S = out
    H *= 255 / 360
    S *= 255
    L *= 255
    for c in out:
        np.round(c, out=c)
    if convert:
        out = list(fromarray(a, "L") for a in out)
    else:
        out = np.asarray(out, dtype=dtype)
    out = [out[0], out[2], out[1]]
    return out

    # H, M, m, C, Cmsk, channels = hsv_split(image, partial=True, dtype=dtype)

    # # Luminance
    # L = np.mean((M, m), 0, dtype=np.int32)

    # # Saturation
    # S = np.zeros(H.shape, dtype=dtype)
    # Lmsk = Cmsk
    # Lmsk &= (L != 1) & (L != 0)
    # S[Lmsk] = np.clip((C[Lmsk] << 8) // (255 - np.abs((L[Lmsk] << 1) - 255)), None, 255)

    # L = L.astype(dtype)

    # out = [H, S, L]
    # if convert:
    #     out = list(fromarray(a, "L") for a in out)
    # return out

def hsi_split(image, convert=True, dtype=np.uint8):
    H, M, m, C, Cmsk, channels = hsv_split(image, partial=True, dtype=dtype)

    # Intensity
    I = np.mean(channels, 0, dtype=np.float32).astype(dtype)

    # Saturation
    S = np.zeros(H.shape, dtype=dtype)
    Imsk = I != 0
    S[Imsk] = 255 - np.clip((m[Imsk] << 8) // I[Imsk], None, 255)

    out = [H, S, I]
    if convert:
        out = list(fromarray(a, "L") for a in out)
    return out

def hcl_split(image, convert=True, dtype=np.uint8):
    out = rgb_split(image, dtype=np.float32)
    out *= 1 / 255
    for r, g, b in zip(*out):
        temp = colorlib.RGB_to_XYZ(r, g, b)
        temp = colorlib.XYZ_to_LUV(*temp)
        l, c, h = colorlib.LUV_to_polarLUV(*temp)
        r[:] = h
        g[:] = c
        b[:] = l
    H, C, L = out
    H *= 255 / 360
    C *= 255 / 180
    L *= 255 / 100
    for c in out:
        np.round(c, out=c)
    if convert:
        out = list(fromarray(a, "L") for a in out)
    else:
        out = np.asarray(out, dtype=dtype)
    return out

def luv_split(image, convert=True, dtype=np.uint8):
    out = rgb_split(image, dtype=np.float32)
    out *= 1 / 255
    for r, g, b in zip(*out):
        temp = colorlib.RGB_to_XYZ(r, g, b)
        l, u, v = colorlib.XYZ_to_LUV(*temp)
        r[:] = l
        g[:] = u
        b[:] = v
    L, U, V = out
    L *= 255 / 100
    U *= 255 / 306
    V *= 255 / 306
    U += 127.5
    V += 127.5
    for c in out:
        np.round(c, out=c)
    if convert:
        out = list(fromarray(a, "L") for a in out)
    else:
        out = np.asarray(out, dtype=dtype)
    return out

def rgb_merge(R, G, B, convert=True):
    out = np.empty(R.shape + (3,), dtype=np.uint8)
    outT = np.moveaxis(out, -1, 0)
    outT[:] = [np.clip(a, None, 255) for a in (R, G, B)]
    if convert:
        out = fromarray(out, "RGB")
    return out

def xyz_merge(X, Y, Z, convert=True):
    X = X.astype(np.float32)
    Y = Y.astype(np.float32)
    Z = Z.astype(np.float32)
    X *= 96 / 255
    Y *= 100 / 255
    Z *= 109 / 255
    for x, y, z in zip(X, Y, Z):
        r, g, b = colorlib.XYZ_to_RGB(x, y, z)
        x[:] = r
        y[:] = g
        z[:] = b
    out = (X, Y, Z)
    for c in out:
        c *= 255
        np.round(c, out=c)
    return rgb_merge(*out, convert=convert)

def hsv_merge(H, S, V, convert=True):
    H = H.astype(np.float32)
    S = S.astype(np.float32)
    V = V.astype(np.float32)
    H *= 360 / 255
    S *= 1 / 255
    V *= 1 / 255
    for h, s, v in zip(H, S, V):
        r, g, b = colorlib.HSV_to_RGB(h, s, v)
        h[:] = r
        s[:] = g
        v[:] = b
    out = (H, S, V)
    for c in out:
        c *= 255
        np.round(c, out=c)
    return rgb_merge(*out, convert=convert)

def hsl_merge(H, S, L, convert=True):
    H = H.astype(np.float32)
    S = S.astype(np.float32)
    L = L.astype(np.float32)
    H *= 360 / 255
    S *= 1 / 255
    L *= 1 / 255
    for h, s, l in zip(H, S, L):
        r, g, b = colorlib.HLS_to_RGB(h, l, s)
        h[:] = r
        s[:] = g
        l[:] = b
    out = (H, S, L)
    for c in out:
        c *= 255
        np.round(c, out=c)
    return rgb_merge(*out, convert=convert)

def hsi_merge(H, S, V, convert=True):
    S = np.asarray(S, dtype=np.float32)
    S *= 1 / 255
    np.clip(S, None, 1, out=S)
    L = np.asarray(L, dtype=np.float32)
    L *= 1 / 255
    np.clip(L, None, 1, out=L)
    H = np.asarray(H, dtype=np.uint8)

    Hp = H.astype(np.float32) * (6 / 256)
    Z = (1 - np.abs(Hp % 2 - 1))
    C = (3 * L * S) / (Z + 1)
    X = C * Z

    # initilize with zero
    R = np.zeros(H.shape, dtype=np.float32)
    G = np.zeros(H.shape, dtype=np.float32)
    B = np.zeros(H.shape, dtype=np.float32)

    # handle each case:
    mask = (Hp < 1)
    # mask = (Hp >= 0) == (Hp < 1)
    R[mask] = C[mask]
    G[mask] = X[mask]
    mask = (1 <= Hp) == (Hp < 2)
    # mask = (Hp >= 1) == (Hp < 2)
    R[mask] = X[mask]
    G[mask] = C[mask]
    mask = (2 <= Hp) == (Hp < 3)
    # mask = (Hp >= 2) == (Hp < 3)
    G[mask] = C[mask]
    B[mask] = X[mask]
    mask = (3 <= Hp) == (Hp < 4)
    # mask = (Hp >= 3) == (Hp < 4)
    G[mask] = X[mask]
    B[mask] = C[mask]
    mask = (4 <= Hp) == (Hp < 5)
    # mask = (Hp >= 4) == (Hp < 5)
    B[mask] = C[mask]
    R[mask] = X[mask]
    mask = (5 <= Hp)
    # mask = (Hp >= 5) == (Hp < 6)
    B[mask] = X[mask]
    R[mask] = C[mask]

    m = L * (1 - S)
    R += m
    G += m
    B += m
    R *= 255
    G *= 255
    B *= 255
    return rgb_merge(R, G, B, convert)

def hcl_merge(H, C, L, convert=True):
    H = H.astype(np.float32)
    C = C.astype(np.float32)
    L = L.astype(np.float32)
    H *= 360 / 255
    C *= 180 / 255
    L *= 100 / 255
    for h, c, l in zip(H, C, L):
        temp = colorlib.polarLUV_to_LUV(l, c, h)
        temp = colorlib.LUV_to_XYZ(*temp)
        r, g, b = colorlib.XYZ_to_RGB(*temp)
        h[:] = r
        c[:] = g
        l[:] = b
    out = (H, C, L)
    for c in out:
        c *= 255
        np.round(c, out=c)
    return rgb_merge(*out, convert=convert)

def luv_merge(L, U, V, convert=True):
    L = L.astype(np.float32)
    U = U.astype(np.float32)
    V = V.astype(np.float32)
    U -= 127.5
    V -= 127.5
    L *= 100 / 255
    U *= 306 / 255
    V *= 306 / 255
    for l, u, v in zip(L, U, V):
        temp = colorlib.LUV_to_XYZ(l, u, v)
        r, g, b = colorlib.XYZ_to_RGB(*temp)
        l[:] = r
        u[:] = g
        v[:] = b
    out = (L, U, V)
    for c in out:
        c *= 255
        np.round(c, out=c)
    return rgb_merge(*out, convert=convert)

srgb_p = ImageCms.createProfile("sRGB")
lab_p  = ImageCms.createProfile("LAB")
# hsv_p  = ImageCms.createProfile("HSV")
rgb2lab = ImageCms.buildTransformFromOpenProfiles(srgb_p, lab_p, "RGB", "LAB")
lab2rgb = ImageCms.buildTransformFromOpenProfiles(lab_p, srgb_p, "LAB", "RGB")
# hsv2lab = ImageCms.buildTransformFromOpenProfiles(hsv_p, lab_p, "HSV", "LAB")
# lab2hsv = ImageCms.buildTransformFromOpenProfiles(lab_p, hsv_p, "LAB", "HSV")

def fromarray(arr, mode="L"):
    try:
        return Image.fromarray(arr, mode=mode)
    except TypeError:
        try:
            b = arr.tobytes()
        except TypeError:
            b = bytes(arr)
        s = tuple(reversed(arr.shape))
        try:
            return Image.frombuffer(mode, s, b, "raw", mode, 0, 1)
        except TypeError:
            return Image.frombytes(mode, s, b)


sizecheck = re.compile("[1-9][0-9]*x[0-9]+")
fpscheck = re.compile("[0-9]+ fps")

def video2img(url, maxsize, fps, out, size=None, dur=None, orig_fps=None, data=None):
    direct = any((size is None, dur is None, orig_fps is None))
    ts = time.time_ns() // 1000
    fn = "cache/" + str(ts)
    if direct:
        if data is None:
            data = get_request(url)
        with open(fn, "wb") as file:
            file.write(data if type(data) is bytes else data.read())
    try:
        if direct:
            try:
                command = ["ffprobe", "-hide_banner", "-v", "error", fn]
                resp = bytes()
                # Up to 3 attempts to get video duration
                for _ in range(3):
                    try:
                        proc = psutil.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        fut = exc.submit(proc.communicate, timeout=12)
                        res = fut.result(timeout=12)
                        resp = bytes().join(res)
                        break
                    except:
                        try:
                            proc.kill()
                        except:
                            pass
                s = resp.decode("utf-8", "replace")
                if orig_fps is None:
                    f = re.findall(fpscheck, s)[0][:-4]
                    orig_fps = float(f)
                if size is None:
                    sfind = re.finditer(sizecheck, s)
                    sizestr = next(sfind).group()
                    size = [int(i) for i in sizestr.split("x")]
            except (ValueError, IndexError):
                if orig_fps is None:
                    orig_fps = 30
                if size is None:
                    size = (960, 540)
        fn2 = fn + ".gif"
        f_in = fn if direct else url
        command = ["ffmpeg", "-threads", "2", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", f_in, "-an", "-vf"]
        w, h = max_size(*size, maxsize)
        fps = fps or orig_fps or 16
        vf = ""
        if w != size[0]:
            vf += "scale=" + str(round(w)) + ":-1:flags=lanczos,"
        vf += "split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
        command.extend([vf, "-loop", "0", "-framerate", str(fps), out])
        print(command)
        subprocess.check_output(command)
        if direct:
            os.remove(fn)
    except:
        if direct:
            try:
                os.remove(fn)
            except:
                pass
        raise

def create_gif(in_type, args, delay):
    ts = time.time_ns() // 1000
    out = "cache/" + str(ts) + ".gif"
    maxsize = 960
    if in_type == "video":
        video2img(args[0], maxsize, round(1000 / delay) if delay else None, out, args[1], args[2], args[3])
        return "$" + out
    images = args
    # Detect if an image sequence or video is being inputted
    imgs = deque()
    for url in images:
        data = get_request(url)
        try:
            img = get_image(data, None)
        except (PIL.UnidentifiedImageError, OverflowError, TypeError):
            if len(data) < 268435456:
                video2img(data, maxsize, round(1000 / delay) if delay else None, out, data=data)
                # $ symbol indicates to return directly
                return "$" + out
            else:
                raise OverflowError("Max file size to load is 256MB.")
        else:
            length = 0
            for f in range(2147483648):
                try:
                    img.seek(f)
                    length = f
                except EOFError:
                    break
            if length != 0 and not delay:
                # maxsize = int(min(maxsize, 32768 / (len(images) + length) ** 0.5))
                delay = img.info.get("duration") or delay or 0.0625
            for f in range(2147483648):
                try:
                    img.seek(f)
                except EOFError:
                    break
                if not imgs:
                    size = max_size(img.width, img.height, maxsize)
                temp = resize_to(img, *size, operation="hamming")
                if type(temp) is ImageSequence:
                    temp = temp._images[temp._position]
                if str(temp.mode) == "RGBA":
                    if imgs and str(imgs[0]) != "RGBA":
                        imgs[0] = imgs[0].convert("RGBA")
                if temp is img:
                    temp = img.crop()
                imgs.append(temp)
    # size = list(imgs[0].size)
    # while size[0] * size[1] * len(imgs) > 8388608:
    #     size[0] /= 2 ** 0.5
    #     size[1] /= 2 ** 0.5
    # size = [round(size[0]), round(size[1])]
    # if imgs[0].size[0] != size[0]:
    #     imgs = (resize_to(img, *size, operation="hamming") for img in imgs)
    if len(imgs) == 1:
        imgs *= 2
    count = len(imgs)
    delay = delay or 0.0625
    return dict(duration=delay * count, count=count, frames=imgs)

def rainbow_gif2(image, duration):
    total = 0
    for f in range(2147483648):
        try:
            image.seek(f)
        except EOFError:
            break
        total += max(image.info.get("duration", 0), 1000 / 60)
    length = f
    loops = total / duration / 1000
    scale = 1
    while abs(loops * scale) < 1:
        scale <<= 1
        if length * scale >= 64:
            loops = 1 if loops >= 0 else -1
            break
    loops = round(loops * scale) / scale
    if abs(loops) < 1:
        loops = 1 if loops >= 0 else -1
    size = image.size
    # print(image, length, scale, loops)

    def rainbow_gif_iterator(image):
        for f in range(length * scale):
            image.seek(f % length)
            if str(image.mode) == "P":
                temp = image.convert("RGBA")
            else:
                temp = image
            if str(image.mode) == "RGBA":
                A = temp.getchannel("A")
            else:
                A = None
            if temp.size[0] != size[0] or temp.size[1] != size[1]:
                temp = temp.resize(size, Image.HAMMING)
            channels = list(temp.convert("HSV").split())
            # channels = hsv_split(temp, convert=False)
            # hue = channels[0] + round(f / length / scale * loops * 256)
            # temp = hsv_merge(hue, *channels[1:])
            channels[0] = channels[0].point(lambda x: int(((f / length / scale * loops + x / 256) % 1) * 256))
            temp = Image.merge("HSV", channels).convert("RGB")
            if A:
                temp.putalpha(A)
            yield temp

    return dict(duration=total * scale, count=length * scale, frames=rainbow_gif_iterator(image))

def rainbow_gif(image, duration):
    try:
        image.seek(1)
    except EOFError:
        image.seek(0)
    else:
        return rainbow_gif2(image, duration)
    # image = resize_max(image, 960, resample=Image.HAMMING)
    # size = list(image.size)
    size = image.size
    if duration == 0:
        fps = 0
    else:
        fps = round(256 / abs(duration))
    rate = 1
    while fps > 48 and rate < 8:
        fps >>= 1
        rate <<= 1
    while fps >= 64:
        fps >>= 1
        rate <<= 1
    if fps <= 0:
        raise ValueError("Invalid framerate value.")
    if str(image.mode) == "P":
        image = image.convert("RGBA")
    if str(image.mode) == "RGBA":
        A = image.getchannel("A")
    else:
        A = None
    channels = list(image.convert("HSV").split())
    # channels = hsv_split(image, convert=False)
    if duration < 0:
        rate = -rate
    count = 256 // abs(rate)
    func = lambda x: (x + rate) & 255

    # Repeatedly hueshift image and return copies
    def rainbow_gif_iterator(image):
        for i in range(0, 256, abs(rate)):
            if i:
                # hue = channels[0] + i
                # image = hsv_merge(hue, *channels[1:])
                channels[0] = channels[0].point(func)
                image = Image.merge("HSV", channels).convert("RGBA")
                if A is not None:
                    image.putalpha(A)
            yield image

    return dict(duration=1000 / fps * count, count=count, frames=rainbow_gif_iterator(image))


def spin_gif2(image, duration):
    total = 0
    for f in range(2147483648):
        try:
            image.seek(f)
        except EOFError:
            break
        total += max(image.info.get("duration", 0), 1000 / 60)
    length = f
    loops = total / duration / 1000
    scale = 1
    while abs(loops * scale) < 1:
        scale *= 2
        if length * scale >= 64:
            loops = 1 if loops >= 0 else -1
            break
    loops = round(loops * scale) / scale
    if abs(loops) < 1:
        loops = 1 if loops >= 0 else -1
    size = image.size

    def spin_gif_iterator(image):
        for f in range(length * scale):
            image.seek(f % length)
            temp = image
            if temp.size[0] != size[0] or temp.size[1] != size[1]:
                temp = temp.resize(size, Image.HAMMING)
            temp = to_circle(rotate_to(temp, f * 360 / length / scale * loops, expand=False))
            yield temp

    return dict(duration=total * scale, count=length * scale, frames=spin_gif_iterator(image))


def spin_gif(image, duration):
    try:
        image.seek(1)
    except EOFError:
        image.seek(0)
    else:
        return spin_gif2(image, duration)
    maxsize = 960
    size = list(image.size)
    if duration == 0:
        fps = 0
    else:
        fps = round(256 / abs(duration))
    rate = 1
    while fps > 32 and rate < 8:
        fps >>= 1
        rate <<= 1
    while fps >= 64:
        fps >>= 1
        rate <<= 1
    if fps <= 0:
        raise ValueError("Invalid framerate value.")
    if duration < 0:
        rate = -rate
    count = 256 // abs(rate)

    # Repeatedly rotate image and return copies
    def spin_gif_iterator(image):
        for i in range(0, 256, abs(rate)):
            if i:
                im = rotate_to(image, i * 360 / 256, expand=False)
            else:
                im = image
            yield to_circle(im)

    return dict(duration=1000 / fps * count, count=count, frames=spin_gif_iterator(image))


def orbit_gif2(image, orbitals, duration, extras):
    total = 0
    for f in range(2147483648):
        try:
            image.seek(f)
        except EOFError:
            break
        total += max(image.info.get("duration", 0), 1000 / 60)
    length = f
    loops = total / duration / 1000
    scale = 1
    while abs(loops * scale) < 1:
        scale *= 2
        if length * scale >= 64:
            loops = 1 if loops >= 0 else -1
            break
    loops = round(loops * scale) / scale
    if abs(loops) < 1:
        loops = 1 if loops >= 0 else -1
    sources = [image]
    sources.extend(extras)

    def orbit_gif_iterator(sources):
        x = orbitals if len(sources) == 1 else 1
        diameter = max(sources[0].size)
        scale2 = orbitals / pi * (sqrt(5) + 1) / 2 + 0.5
        size = (round(diameter * scale2),) * 2
        for f in range(0, length * scale):
            im = Image.new("RGBA", size, (0,) * 4)
            if orbitals > 1:
                im2 = Image.new("RGBA", size, (0,) * 4)
                if orbitals & 1:
                    im3 = Image.new("RGBA", size, (0,) * 4)
            for j in range(orbitals):
                image = sources[j % len(sources)]
                if hasattr(image, "length"):
                    g = f % image.length
                else:
                    g = f
                try:
                    image.seek(g)
                except EOFError:
                    image.length = f
                    image.seek(0)
                image = resize_max(image, diameter, force=True)
                angle = f / length / scale * loops * tau / x + j / orbitals * tau
                pos = im.width / 2 + np.array((cos(angle), sin(angle))) * (diameter * scale2 / 2 - diameter / 2) - (image.width / 2, image.height / 2)
                pos = list(map(round, pos))
                if j == orbitals - 1 and orbitals & 1 and orbitals > 1:
                    im3.paste(image, pos)
                elif not j & 1:
                    im.paste(image, pos)
                else:
                    im2.paste(image, pos)
            if orbitals > 1:
                if orbitals & 1:
                    im2 = Image.alpha_composite(im3, im2)
                im = Image.alpha_composite(im, im2)
            yield im

    return dict(duration=total * scale, count=length * scale, frames=orbit_gif_iterator(sources))


def orbit_gif(image, orbitals, duration, extras):
    if extras:
        extras = [get_image(url, url) for url in extras[:orbitals]]
    else:
        duration /= orbitals
    try:
        image.seek(1)
    except EOFError:
        image.seek(0)
    else:
        return orbit_gif2(image, orbitals, duration, extras)
    maxsize = 960
    size = list(image.size)
    if duration == 0:
        fps = 0
    else:
        fps = round(256 / abs(duration))
    rate = 1
    while fps > 32 and rate < 8:
        fps >>= 1
        rate <<= 1
    while fps >= 64:
        fps >>= 1
        rate <<= 1
    if fps <= 0:
        raise ValueError("Invalid framerate value.")
    if duration < 0:
        rate = -rate
    count = 256 // abs(rate)
    sources = [image]
    sources.extend(extras)

    # Repeatedly rotate image and return copies
    def orbit_gif_iterator(sources):
        x = orbitals if len(sources) == 1 else 1
        diameter = max(sources[0].size)
        scale = orbitals / pi * (sqrt(5) + 1) / 2 + 0.5
        size = (round(diameter * scale),) * 2
        for i in range(0, 256, abs(rate)):
            im = Image.new("RGBA", size, (0,) * 4)
            if orbitals > 1:
                im2 = Image.new("RGBA", size, (0,) * 4)
                if orbitals & 1:
                    im3 = Image.new("RGBA", size, (0,) * 4)
            for j in range(orbitals):
                image = sources[j % len(sources)]
                image = resize_max(image, diameter, force=True)
                angle = i / 256 * tau / x + j / orbitals * tau
                pos = im.width / 2 + np.array((cos(angle), sin(angle))) * (diameter * scale / 2 - diameter / 2) - (image.width / 2, image.height / 2)
                pos = list(map(round, pos))
                if j == orbitals - 1 and orbitals & 1 and orbitals > 1:
                    im3.paste(image, pos)
                elif not j & 1:
                    im.paste(image, pos)
                else:
                    im2.paste(image, pos)
            if orbitals > 1:
                if orbitals & 1:
                    im2 = Image.alpha_composite(im3, im2)
                im = Image.alpha_composite(im, im2)
            yield im

    return dict(duration=1000 / fps * count, count=count, frames=orbit_gif_iterator(sources))


def to_square(image):
    w, h = image.size
    d = w - h
    if not d:
        return image
    if d > 0:
        return image.crop((d >> 1, 0, w - (1 + d >> 1), h))
    return image.crop((0, -d >> 1, w, h - (1 - d >> 1)))


CIRCLE_CACHE = {}

def to_circle(image):
    global CIRCLE_CACHE
    if str(image.mode) != "RGBA":
        image = to_square(image).convert("RGBA")
    else:
        image = to_square(image)
    try:
        image_map = CIRCLE_CACHE[image.size]
    except KeyError:
        image_map = Image.new("RGBA", image.size)
        draw = ImageDraw.Draw(image_map)
        draw.ellipse((0, 0, *image.size), outline=0, fill=(255,) * 4, width=0)
        CIRCLE_CACHE[image.size] = image_map
    return ImageChops.multiply(image, image_map)


DIRECTIONS = dict(
    left=0,
    up=1,
    right=2,
    down=3,
    l=0,
    u=1,
    r=2,
    d=3,
)
DIRECTIONS.update({
    "0": 0,
    "1": 1,
    "2": 2,
    "3": 3,
})

def scroll_gif2(image, direction, duration):
    total = 0
    for f in range(2147483647):
        try:
            image.seek(f)
        except EOFError:
            break
        dur = max(image.info.get("duration", 0), 1000 / 60)
        total += dur
    count = f

    def scroll_gif_iterator(image):
        if direction & 1:
            y = (direction & 2) - 1
            x = 0
        else:
            x = (direction & 2) - 1
            y = 0
        for i in range(count):
            image.seek(i)
            temp = resize_max(image, 960, resample=Image.HAMMING)
            if i:
                xm = round(x * temp.width / count * i)
                ym = round(y * temp.height / count * i)
                temp = ImageChops.offset(temp, xm, ym)
            yield temp

    return dict(duration=total, count=count, frames=scroll_gif_iterator(image))

def scroll_gif(image, direction, duration, fps):
    try:
        direction = DIRECTIONS[direction.casefold()]
    except KeyError:
        raise TypeError(f"Invalid direction {direction}")
    try:
        image.seek(1)
    except EOFError:
        image.seek(0)
    else:
        return scroll_gif2(image, direction, duration)
    image = resize_max(image, 960, resample=Image.HAMMING)
    count = round(duration * fps)

    def scroll_gif_iterator(image):
        yield image
        if direction & 1:
            y = (direction & 2) - 1
            x = 0
        else:
            x = (direction & 2) - 1
            y = 0
        for i in range(1, count):
            xm = round(x * image.width / count * i)
            ym = round(y * image.height / count * i)
            temp = ImageChops.offset(image, xm, ym)
            yield temp

    return dict(duration=1000 * duration, count=count, frames=scroll_gif_iterator(image))


def magik_gif2(image, cell_count, grid_distance, iterations):
    total = 0
    for f in range(2147483648):
        try:
            image.seek(f)
        except EOFError:
            break
        total += max(image.info.get("duration", 0), 1000 / 60)
    length = f
    loops = total / 2 / 1000
    scale = 1
    while abs(loops * scale) < 1:
        scale *= 2
        if length * scale >= 32:
            loops = 1 if loops >= 0 else -1
            break
    loops = round(loops * scale) / scale
    if abs(loops) < 1:
        loops = 1 if loops >= 0 else -1
    size = image.size

    def magik_gif_iterator(image):
        ts = time.time_ns() // 1000
        for f in range(length * scale):
            np.random.seed(ts & 4294967295)
            image.seek(f % length)
            temp = image
            if temp.size[0] != size[0] or temp.size[1] != size[1]:
                temp = temp.resize(size, Image.HAMMING)
            for _ in range(int(31 * iterations * f / length / scale)):
                dst_grid = griddify(shape_to_rect(image.size), cell_count, cell_count)
                src_grid = distort_grid(dst_grid, grid_distance)
                mesh = grid_to_mesh(src_grid, dst_grid)
                temp = temp.transform(temp.size, Image.MESH, mesh, resample=Image.NEAREST)
            yield temp

    return dict(duration=total * scale, count=length * scale, frames=magik_gif_iterator(image))


def magik_gif(image, cell_count=7, iterations=1):
    grid_distance = int(max(1, round(sqrt(np.prod(image.size)) / cell_count / 3 / iterations)))
    try:
        image.seek(1)
    except EOFError:
        image.seek(0)
    else:
        return magik_gif2(image, cell_count, grid_distance, iterations)
    image = resize_max(image, 960, resample=Image.HAMMING)

    def magik_gif_iterator(image):
        yield image
        for _ in range(31):
            for _ in range(iterations):
                dst_grid = griddify(shape_to_rect(image.size), cell_count, cell_count)
                src_grid = distort_grid(dst_grid, grid_distance)
                mesh = grid_to_mesh(src_grid, dst_grid)
                image = image.transform(image.size, Image.MESH, mesh, resample=Image.NEAREST)
            yield image

    return dict(duration=2000, count=32, frames=magik_gif_iterator(image))


def quad_as_rect(quad):
    if quad[0] != quad[2]: return False
    if quad[1] != quad[7]: return False
    if quad[4] != quad[6]: return False
    if quad[3] != quad[5]: return False
    return True

def quad_to_rect(quad):
    assert(len(quad) == 8)
    assert(quad_as_rect(quad))
    return (quad[0], quad[1], quad[4], quad[3])

def rect_to_quad(rect):
    assert(len(rect) == 4)
    return (rect[0], rect[1], rect[0], rect[3], rect[2], rect[3], rect[2], rect[1])

def shape_to_rect(shape):
    assert(len(shape) == 2)
    return (0, 0, shape[0], shape[1])

def griddify(rect, w_div, h_div):
    w = rect[2] - rect[0]
    h = rect[3] - rect[1]
    x_step = w / float(w_div)
    y_step = h / float(h_div)
    y = rect[1]
    grid_vertex_matrix = deque()
    for _ in range(h_div + 1):
        grid_vertex_matrix.append(deque())
        x = rect[0]
        for _ in range(w_div + 1):
            grid_vertex_matrix[-1].append([int(x), int(y)])
            x += x_step
        y += y_step
    grid = np.array(grid_vertex_matrix)
    return grid

def distort_grid(org_grid, max_shift):
    new_grid = np.copy(org_grid)
    x_min = np.min(new_grid[:, :, 0])
    y_min = np.min(new_grid[:, :, 1])
    x_max = np.max(new_grid[:, :, 0])
    y_max = np.max(new_grid[:, :, 1])
    new_grid += np.random.randint(-max_shift, max_shift + 1, new_grid.shape)
    new_grid[:, :, 0] = np.maximum(x_min, new_grid[:, :, 0])
    new_grid[:, :, 1] = np.maximum(y_min, new_grid[:, :, 1])
    new_grid[:, :, 0] = np.minimum(x_max, new_grid[:, :, 0])
    new_grid[:, :, 1] = np.minimum(y_max, new_grid[:, :, 1])
    return new_grid

def grid_to_mesh(src_grid, dst_grid):
    assert(src_grid.shape == dst_grid.shape)
    mesh = deque()
    for i in range(src_grid.shape[0] - 1):
        for j in range(src_grid.shape[1] - 1):
            src_quad = [src_grid[i    , j    , 0], src_grid[i    , j    , 1],
                        src_grid[i + 1, j    , 0], src_grid[i + 1, j    , 1],
                        src_grid[i + 1, j + 1, 0], src_grid[i + 1, j + 1, 1],
                        src_grid[i    , j + 1, 0], src_grid[i    , j + 1, 1]]
            dst_quad = [dst_grid[i    , j    , 0], dst_grid[i    , j    , 1],
                        dst_grid[i + 1, j    , 0], dst_grid[i + 1, j    , 1],
                        dst_grid[i + 1, j + 1, 0], dst_grid[i + 1, j + 1, 1],
                        dst_grid[i    , j + 1, 0], dst_grid[i    , j + 1, 1]]
            dst_rect = quad_to_rect(dst_quad)
            mesh.append([dst_rect, src_quad])
    return list(mesh)

def magik(image, cell_count=7):
    dst_grid = griddify(shape_to_rect(image.size), cell_count, cell_count)
    src_grid = distort_grid(dst_grid, int(max(1, round(sqrt(np.prod(image.size)) / cell_count / 3))))
    mesh = grid_to_mesh(src_grid, dst_grid)
    return image.transform(image.size, Image.MESH, mesh, resample=Image.NEAREST)


blurs = {
    "box": ImageFilter.BoxBlur,
    "boxblur": ImageFilter.BoxBlur,
    "gaussian": ImageFilter.GaussianBlur,
    "gaussianblur": ImageFilter.GaussianBlur,
}

def blur(image, filt="box", radius=2):
    try:
        _filt = blurs[filt.replace("_", "").casefold()]
    except KeyError:
        raise TypeError(f'Invalid image operation: "{filt}"')
    return image.filter(_filt(radius))


def invert(image):
    if str(image.mode) == "P":
        image = image.convert("RGBA")
    if str(image.mode) == "RGBA":
        A = image.getchannel("A")
        image = image.convert("RGB")
    else:
        A = None
    image = ImageOps.invert(image)
    if A is not None:
        image.putalpha(A)
    return image

def greyscale(image):
    if str(image.mode) == "P":
        image = image.convert("RGBA")
    if str(image.mode) == "RGBA":
        A = image.getchannel("A")
    else:
        A = None
    image = ImageOps.grayscale(image)
    if A is not None:
        if str(image.mode) != "L":
            image = image.getchannel("R")
        image = Image.merge("RGBA", (image, image, image, A))
    return image

def laplacian(image):
    if str(image.mode) == "P":
        image = image.convert("RGBA")
    b = image.tobytes()
    surf = pygame.image.frombuffer(b, image.size, image.mode)
    surf = pygame.transform.laplacian(surf)
    b = pygame.image.tostring(surf, image.mode)
    image = Image.frombuffer(image.mode, image.size, b)
    return image

def colourspace(image, source, dest):
    if str(image.mode) == "P":
        image = image.convert("RGBA")
    if str(image.mode) == "RGBA":
        A = image.getchannel("A")
    else:
        A = None
    out = None
    if source == "rgb":
        if dest == "cmy":
            out = invert(image)
        elif dest == "xyz":
            spl = xyz_split(image, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsv":
            spl = image.convert("HSV").tobytes()
            out = Image.frombytes("RGB", image.size, spl)
        elif dest == "hsl":
            spl = hsl_split(image, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsi":
            spl = hsi_split(image, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hcl":
            spl = hcl_split(image, convert=False)
            out = rgb_merge(*spl)
        elif dest == "lab":
            spl = ImageCms.applyTransform(image, rgb2lab).tobytes()
            out = Image.frombytes("RGB", image.size, spl)
        elif dest == "luv":
            spl = luv_split(image, convert=False)
            out = rgb_merge(*spl)
    elif source == "cmy":
        if dest == "rgb":
            out = invert(image)
        elif dest == "xyz":
            image = invert(image)
            spl = xyz_split(image, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsv":
            spl = invert(image).convert("HSV").tobytes()
            out = Image.frombytes("RGB", image.size, spl)
        elif dest == "hsl":
            image = invert(image)
            spl = hsl_split(image, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsi":
            image = invert(image)
            spl = hsi_split(image, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hcl":
            image = invert(image)
            spl = hcl_split(image, convert=False)
            out = rgb_merge(*spl)
        elif dest == "lab":
            spl = ImageCms.applyTransform(invert(image), rgb2lab).tobytes()
            out = Image.frombytes("RGB", image.size, spl)
        elif dest == "luv":
            image = invert(image)
            spl = luv_split(image, convert=False)
            out = rgb_merge(*spl)
    elif source == "xyz":
        if dest == "rgb":
            spl = rgb_split(image)
            out = xyz_merge(*spl)
        elif dest == "cmy":
            spl = rgb_split(image)
            out = xyz_merge(*spl, convert=False)
            out ^= 255
            out = fromarray(out, "RGB")
        elif dest == "hsv":
            spl = rgb_split(image)
            im = xyz_merge(*spl)
            out = im.convert("HSV")
        elif dest == "hsl":
            spl = rgb_split(image)
            im = xyz_merge(*spl)
            spl = hsl_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsi":
            spl = rgb_split(image)
            im = xyz_merge(*spl)
            spl = hsi_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hcl":
            spl = rgb_split(image)
            im = xyz_merge(*spl)
            spl = hcl_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "lab":
            spl = rgb_split(image)
            im = xyz_merge(*spl)
            spl = ImageCms.applyTransform(im, rgb2lab).tobytes()
            out = Image.frombytes("RGB", image.size, spl)
        elif dest == "luv":
            spl = rgb_split(image)
            im = xyz_merge(*spl)
            spl = luv_split(im, convert=False)
            out = rgb_merge(*spl)
    elif source == "hsv":
        if dest == "rgb":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            out = Image.frombytes("HSV", image.size, spl).convert("RGB")
        elif dest == "cmy":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            out = invert(Image.frombytes("HSV", image.size, spl).convert("RGB"))
        elif dest == "xyz":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            im = Image.frombytes("HSV", image.size, spl).convert("RGB")
            spl = xyz_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsl":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            im = Image.frombytes("HSV", image.size, spl).convert("RGB")
            spl = hsl_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsi":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            im = Image.frombytes("HSV", image.size, spl).convert("RGB")
            spl = hsi_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hcl":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            im = Image.frombytes("HSV", image.size, spl).convert("RGB")
            spl = hcl_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "lab":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            im = Image.frombytes("HSV", image.size, spl)
            spl = ImageCms.applyTransform(im.convert("RGB"), rgb2lab).tobytes()
            out = Image.frombytes("RGB", image.size, spl)
        elif dest == "luv":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            im = Image.frombytes("HSV", image.size, spl).convert("RGB")
            spl = luv_split(im, convert=False)
            out = rgb_merge(*spl)
    elif source == "hsl":
        if dest == "rgb":
            spl = rgb_split(image)
            out = hsl_merge(*spl)
        elif dest == "cmy":
            spl = rgb_split(image)
            out = hsl_merge(*spl, convert=False)
            out ^= 255
            out = fromarray(out, "RGB")
        elif dest == "xyz":
            spl = rgb_split(image)
            im = hsl_merge(*spl)
            spl = xyz_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsv":
            spl = rgb_split(image)
            im = hsl_merge(*spl)
            out = im.convert("HSV")
        elif dest == "hsi":
            spl = rgb_split(image)
            im = hsl_merge(*spl)
            spl = hsi_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hcl":
            spl = rgb_split(image)
            im = hsl_merge(*spl)
            spl = hcl_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "lab":
            spl = rgb_split(image)
            im = hsl_merge(*spl)
            spl = ImageCms.applyTransform(im, rgb2lab).tobytes()
            out = Image.frombytes("RGB", image.size, spl)
        elif dest == "luv":
            spl = rgb_split(image)
            im = hsl_merge(*spl)
            spl = luv_split(im, convert=False)
            out = rgb_merge(*spl)
    elif source == "hsi":
        if dest == "rgb":
            spl = rgb_split(image)
            out = hsi_merge(*spl)
        elif dest == "cmy":
            spl = rgb_split(image)
            out = hsi_merge(*spl, convert=False)
            out ^= 255
            out = fromarray(out, "RGB")
        elif dest == "xyz":
            spl = rgb_split(image)
            im = hsi_merge(*spl)
            spl = xyz_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsv":
            spl = rgb_split(image)
            im = hsi_merge(*spl)
            out = im.convert("HSV")
        elif dest == "hsl":
            spl = rgb_split(image)
            im = hsi_merge(*spl)
            spl = hsl_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hcl":
            spl = rgb_split(image)
            im = hsi_merge(*spl)
            spl = hcl_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "lab":
            spl = rgb_split(image)
            im = hsi_merge(*spl)
            spl = ImageCms.applyTransform(im, rgb2lab).tobytes()
            out = Image.frombytes("RGB", image.size, spl)
        elif dest == "luv":
            spl = rgb_split(image)
            im = hsi_merge(*spl)
            spl = luv_split(im, convert=False)
            out = rgb_merge(*spl)
    elif source == "hcl":
        if dest == "rgb":
            spl = rgb_split(image)
            out = hcl_merge(*spl)
        elif dest == "cmy":
            spl = rgb_split(image)
            out = hcl_merge(*spl, convert=False)
            out ^= 255
            out = fromarray(out, "RGB")
        elif dest == "xyz":
            spl = rgb_split(image)
            im = hcl_merge(*spl)
            spl = xyz_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsv":
            spl = rgb_split(image)
            im = hcl_merge(*spl)
            out = im.convert("HSV")
        elif dest == "hsl":
            spl = rgb_split(image)
            im = hcl_merge(*spl)
            spl = hsl_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsi":
            spl = rgb_split(image)
            im = hcl_merge(*spl)
            spl = hsi_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "lab":
            spl = rgb_split(image)
            im = hcl_merge(*spl)
            spl = ImageCms.applyTransform(im, rgb2lab).tobytes()
            out = Image.frombytes("RGB", image.size, spl)
        elif dest == "luv":
            spl = rgb_split(image)
            im = hcl_merge(*spl)
            spl = luv_split(im, convert=False)
            out = rgb_merge(*spl)
    elif source == "lab":
        if dest == "rgb":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            out = ImageCms.applyTransform(Image.frombytes("LAB", image.size, spl), lab2rgb)
        elif dest == "cmy":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            out = invert(ImageCms.applyTransform(Image.frombytes("LAB", image.size, spl), lab2rgb))
        elif dest == "xyz":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            im = ImageCms.applyTransform(Image.frombytes("LAB", image.size, spl), lab2rgb)
            spl = xyz_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsv":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            im = ImageCms.applyTransform(Image.frombytes("LAB", image.size, spl), lab2rgb)
            spl = im.convert("HSV").tobytes()
            out = Image.frombytes("RGB", image.size, spl)
        elif dest == "hsl":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            im = ImageCms.applyTransform(Image.frombytes("LAB", image.size, spl), lab2rgb)
            spl = hsl_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsi":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            im = ImageCms.applyTransform(Image.frombytes("LAB", image.size, spl), lab2rgb)
            spl = hsi_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hcl":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            im = ImageCms.applyTransform(Image.frombytes("LAB", image.size, spl), lab2rgb)
            spl = hcl_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "luv":
            if image.mode != "RGB":
                image = image.convert("RGB")
            spl = image.tobytes()
            im = ImageCms.applyTransform(Image.frombytes("LAB", image.size, spl), lab2rgb)
            spl = luv_split(im, convert=False)
            out = rgb_merge(*spl)
    elif source == "luv":
        if dest == "rgb":
            spl = rgb_split(image)
            out = luv_merge(*spl)
        elif dest == "cmy":
            spl = rgb_split(image)
            out = luv_merge(*spl, convert=False)
            out ^= 255
            out = fromarray(out, "RGB")
        elif dest == "xyz":
            spl = rgb_split(image)
            im = luv_merge(*spl)
            spl = xyz_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsv":
            spl = rgb_split(image)
            im = luv_merge(*spl)
            out = im.convert("HSV")
        elif dest == "hsl":
            spl = rgb_split(image)
            im = luv_merge(*spl)
            spl = hsl_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hsi":
            spl = rgb_split(image)
            im = luv_merge(*spl)
            spl = hsi_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "hcl":
            spl = rgb_split(image)
            im = luv_merge(*spl)
            spl = hcl_split(im, convert=False)
            out = rgb_merge(*spl)
        elif dest == "lab":
            spl = rgb_split(image)
            im = luv_merge(*spl)
            spl = ImageCms.applyTransform(im, rgb2lab).tobytes()
            out = Image.frombytes("RGB", image.size, spl)
    if not out:
        raise NotImplementedError(f"Image conversion from {source} to {dest} is not currently supported.")
    if A is not None:
        out.putalpha(A)
    return out


# Autodetect max image size, keeping aspect ratio
def max_size(w, h, maxsize, force=False):
    s = w * h
    m = maxsize * maxsize
    if s > m or force:
        r = (m / s) ** 0.5
        w = round(w * r)
        h = round(h * r)
    return w, h

def resize_max(image, maxsize, resample=Image.LANCZOS, box=None, reducing_gap=None, force=False):
    w, h = max_size(image.width, image.height, maxsize, force=force)
    if w != image.width or h != image.height:
        if type(resample) is str:
            image = resize_to(image, w, h, resample)
        else:
            image = image.resize([w, h], resample, box, reducing_gap)
    return image

resizers = dict(
    sinc=Image.LANCZOS,
    lanczos=Image.LANCZOS,
    cubic=Image.BICUBIC,
    bicubic=Image.BICUBIC,
    scale2x="scale2x",
    hamming=Image.HAMMING,
    linear=Image.BILINEAR,
    bilinear=Image.BILINEAR,
    nearest=Image.NEAREST,
    nearestneighbour=Image.NEAREST,
    crop="crop",
    padding="crop",
)

def resize_mult(image, x, y, operation):
    if x == y == 1:
        return image
    w = image.width * x
    h = image.height * y
    return resize_to(image, round(w), round(h), operation)

def resize_to(image, w, h, operation="auto"):
    if abs(w * h) > 1073741824:
        raise OverflowError("Resulting image size too large.")
    if w == image.width and h == image.height:
        return image
    op = operation.casefold().replace(" ", "").replace("_", "")
    if op in resizers:
        filt = resizers[op]
    elif op == "auto":
        # Choose resampling algorithm based on source/destination image sizes
        m = min(abs(w), abs(h))
        n = min(image.width, image.height)
        if n > m:
            m = n
        if m <= 512:
            filt = "scale2x"
        elif m <= 3072:
            filt = Image.LANCZOS
        elif m <= 4096:
            filt = Image.BICUBIC
        else:
            filt = Image.BILINEAR
    else:
        raise TypeError(f'Invalid image operation: "{op}"')
    if w < 0:
        w = -w
        image = ImageOps.mirror(image)
    if h < 0:
        h = -h
        image = ImageOps.flip(image)
    if filt != Image.NEAREST:
        if str(image.mode) == "P":
            image = image.convert("RGBA")
    if filt == "scale2x":
        if w > image.width or h > image.height:
            if image.mode == "P":
                image = image.convert("RGBA")
            b = image.tobytes()
            surf = pygame.image.frombuffer(b, image.size, image.mode)
            factor = 0
            while w > surf.get_width() or h > surf.get_height():
                surf = pygame.transform.scale2x(surf)
                factor += 1
                if factor >= 2:
                    break
            b = pygame.image.tostring(surf, image.mode)
            image = Image.frombuffer(image.mode, surf.get_size(), b)
        if image.size == (w, h):
            return image
        filt = Image.NEAREST if w > image.width and h > image.height else Image.HAMMING
    elif filt == "crop":
        if image.mode == "P":
            image = image.convert("RGBA")
        out = Image.new(image.mode, (w, h), (0,) * len(image.mode))
        pos = tuple(np.array((w, h)) - image.size >> 1)
        out.paste(image, pos)
        return out
    return image.resize([w, h], filt)

def rotate_to(image, angle, expand=True):
    angle %= 360
    if not angle % 90:
        if angle == 90:
            return image.transpose(Image.ROTATE_90)
        elif angle == 180:
            return image.transpose(Image.ROTATE_180)
        elif angle == 270:
            return image.transpose(Image.ROTATE_270)
        return image
    return image.rotate(angle, resample=Image.BICUBIC, expand=expand)


def get_colour(image):
    if "A" in str(image.mode):
        spl = deque(image.split())
        A = np.divide(spl.pop(), 255)
        sumA = np.sum(A)
        if sumA == 0:
            col = [0, 0, 0]
        else:
            col = [np.sum(np.multiply(channel, A)) / sumA for channel in spl]
    else:
        spl = image.split()
        col = [np.mean(channel) for channel in spl]
    return str(col)


channel_map = {
    "alpha": -1,
    "a": -1,
    "red": 0,
    "r": 0,
    "green": 1,
    "g": 1,
    "blue": 2,
    "b": 2,
    "cyan": 3,
    "c": 3,
    "magenta": 4,
    "m": 4,
    "yellow": 5,
    "y": 5,
    "hue": 6,
    "h": 6,
    "saturation": 7,
    "sat": 7,
    "s": 7,
    "value": 8,
    "v": 8,
    "lightness": 9,
    "luminance": 9,
    "lum": 9,
    "l": 9,
}

def fill_channels(image, colour, *channels):
    channels = list(channels)
    ops = {}
    for c in channels:
        try:
            cid = channel_map[c]
        except KeyError:
            if len(c) <= 1:
                raise TypeError("invalid colour identifier: " + c)
            channels.extend(c)
        else:
            ops[cid] = None
    ch = Image.new("L", image.size, colour)
    if "RGB" not in str(image.mode):
        image = image.convert("RGB")
    if -1 in ops:
        image.putalpha(ch)
    mode = image.mode
    rgb = False
    for i in range(3):
        if i in ops:
            rgb = True
    if rgb:
        spl = list(image.split())
        for i in range(3):
            if i in ops:
                spl[i] = ch
        image = Image.merge(mode, spl)
    cmy = False
    for i in range(3, 6):
        if i in ops:
            cmy = True
    if cmy:
        spl = list(ImageChops.invert(image).split())
        for i in range(3, 6):
            if i in ops:
                spl[i - 3] = ch
        image = ImageChops.invert(Image.merge(mode, spl))
    hsv = False
    for i in range(6, 9):
        if i in ops:
            hsv = True
    if hsv:
        if str(image.mode) == "P":
            image = image.convert("RGBA")
        if str(image.mode) == "RGBA":
            A = image.getchannel("A")
        else:
            A = None
        spl = list(image.convert("HSV").split())
        # spl = hsv_split(image, convert=False)
        for i in range(6, 9):
            if i in ops:
                spl[i - 6] = ch
        # image = hsv_merge(*spl)
        image = Image.merge("HSV", spl).convert("RGB")
        if A is not None:
            image.putalpha(A)
    if 9 in ops:
        if str(image.mode) == "P":
            image = image.convert("RGBA")
        if str(image.mode) == "RGBA":
            A = image.getchannel("A")
        else:
            A = None
        spl = hsl_split(image, convert=False)
        spl[-1] = np.full(tuple(reversed(image.size)), colour)
        image = hsl_merge(*spl)
        if A is not None:
            image.putalpha(A)
    return image


# Image blend operations (this is a bit of a mess)
blenders = {
    "normal": "blend",
    "blt": "blend",
    "blit": "blend",
    "blend": "blend",
    "replace": "replace",
    "+": "add",
    "add": "add",
    "addition": "add",
    "-": "subtract",
    "sub": "subtract",
    "subtract": "subtract",
    "subtraction": "subtract",
    "*": "multiply",
    "mul": "multiply",
    "mult": "multiply",
    "multiply": "multiply",
    "multiplication": "multiply",
    "/": blend_modes.divide,
    "div": blend_modes.divide,
    "divide": blend_modes.divide,
    "division": blend_modes.divide,
    "mod": "OP_X%Y",
    "modulo": "OP_X%Y",
    "%": "OP_X%Y",
    "and": "OP_X&Y",
    "&": "OP_X&Y",
    "or": "OP_X|Y",
    "|": "OP_X|Y",
    "xor": "OP_X^Y",
    "^": "OP_X^Y",
    "nand": "OP_255-(X&Y)",
    "~&": "OP_255-(X&Y)",
    "nor": "OP_255-(X|Y)",
    "~|": "OP_255-(X|Y)",
    "xnor": "OP_255-(X^Y)",
    "~^": "OP_255-(X^Y)",
    "xand": "OP_255-(X^Y)",
    "diff": "difference",
    "difference": "difference",
    "overlay": blend_modes.overlay,
    "screen": "screen",
    "soft": blend_modes.soft_light,
    "softlight": blend_modes.soft_light,
    "hard": blend_modes.hard_light,
    "hardlight": blend_modes.hard_light,
    "lighter": "lighter",
    "lighten": "lighter",
    "darker": "darker",
    "darken": "darker",
    "plusdarker": "OP_X+Y-255",
    "plusdarken": "OP_X+Y-255",
    "overflow": "OVERFLOW",
    "lighting": "LIGHTING",
    "extract": blend_modes.grain_extract,
    "grainextract": blend_modes.grain_extract,
    "merge": blend_modes.grain_merge,
    "grainmerge": blend_modes.grain_merge,
    "burn": "OP_255*(1-((255-Y)/X))",
    "colorburn": "OP_255*(1-((255-Y)/X))",
    "colourburn": "OP_255*(1-((255-Y)/X))",
    "linearburn": "OP_(X+Y)-255",
    "dodge": blend_modes.dodge,
    "colordodge": blend_modes.dodge,
    "colourdodge": blend_modes.dodge,
    "lineardodge": "add",
    "hue": "SP_HUE",
    "sat": "SP_SAT",
    "saturation": "SP_SAT",
    "lum": "SP_LUM",
    "luminosity": "SP_LUM",
    "val": "SP_VAL",
    "value": "SP_VAL",
    "color": "SP_COL",
    "colour": "SP_COL",
    "alpha": "SP_ALP",
}
halve = (np.arange(1, 257) >> 1).astype(np.uint8)
darken = np.concatenate((np.zeros(128, dtype=np.uint8), np.arange(128, dtype=np.uint8)))

def blend_op(image, url, operation, amount, recursive=True):
    op = operation.casefold().replace(" ", "").replace("_", "")
    if op in blenders:
        filt = blenders[op]
    elif op == "auto":
        filt = "blend"
    else:
        raise TypeError("Invalid image operation: \"" + op + '"')
    image2 = get_image(url, url)
    if recursive:
        if not globals()["ANIM"]:
            try:
                image2.seek(1)
            except EOFError:
                image2.seek(0)
            else:
                dur = 0
                for f in range(2147483648):
                    try:
                        image2.seek(f)
                    except EOFError:
                        break
                    dur += max(image2.info.get("duration", 0), 1000 / 60)
                count = f

                def blend_op_iterator(image, image2, operation, amount):
                    for f in range(2147483648):
                        try:
                            image2.seek(f)
                        except EOFError:
                            break
                        if str(image.mode) == "P":
                            image = image.convert("RGBA")
                        elif str(image.mode) != "RGBA":
                            temp = image.convert("RGBA")
                        else:
                            temp = image
                        temp2 = image2._images[image2._position]
                        # print(image2._position)
                        # image2._images[image2._position].save(f"temp{f}.png")
                        yield blend_op(temp, temp2, operation, amount, recursive=False)

                return dict(duration=dur, count=count, frames=blend_op_iterator(image, image2, operation, amount))
        try:
            n_frames = 1
            for f in range(CURRENT_FRAME + 1):
                try:
                    image2.seek(f)
                except EOFError:
                    break
                n_frames += 1
            image2.seek(CURRENT_FRAME % n_frames)
        except EOFError:
            image2.seek(0)
    if image2.width != image.width or image2.height != image.height:
        image2 = resize_to(image2, image.width, image.height, "auto")
    if type(filt) is not str:
        if str(image.mode) == "P":
            image = image.convert("RGBA")
        if str(image.mode) != "RGBA":
            image = image.convert("RGBA")
        if str(image2.mode) == "P" and "transparency" in image2.info:
            image2 = image2.convert("RGBA")
        if str(image2.mode) != "RGBA":
            image2 = image2.convert("RGBA")
        imgA = np.array(image).astype(np.float64)
        imgB = np.array(image2).astype(np.float64)
        out = fromarray(np.uint8(filt(imgA, imgB, amount)), image.mode)
    else:
        # Basic blend, use second image
        if filt in ("blend", "replace"):
            out = image2
        # Image operation, use ImageMath.eval
        elif filt.startswith("OP_"):
            f = filt[3:]
            if str(image.mode) != str(image2.mode):
                if str(image.mode) == "P":
                    image = image.convert("RGBA")
                if str(image.mode) != "RGBA":
                    image = image.convert("RGBA")
                if str(image2.mode) == "P" and "transparency" in image2.info:
                    image2 = image2.convert("RGBA")
                if str(image2.mode) != "RGBA":
                    image2 = image2.convert("RGBA")
            mode = image.mode
            ch1 = image.split()
            ch2 = image2.split()
            c = len(ch1)
            ch3 = [ImageMath.eval(f, dict(X=ch1[i], Y=ch2[i])).convert("L") for i in range(3)]
            if c > 3:
                ch3.append(ImageMath.eval("max(X,Y)", dict(X=ch1[-1], Y=ch2[-1])).convert("L"))
            out = Image.merge(mode, ch3)
        # Special operation, use HSV channels
        elif filt.startswith("SP_"):
            f = filt[3:]
            if f == "ALP":
                if "A" in image2.mode:
                    if amount % 1:
                        out = image.copy()
                    else:
                        out = image
                    out.putalpha(image2.getchannel("A"))
                else:
                    out = image
                    amount = 0
            else:
                if str(image.mode) == "P":
                    image = image.convert("RGBA")
                if str(image.mode) == "RGBA":
                    A1 = image.getchannel("A")
                else:
                    A1 = None
                if str(image2.mode) == "P" and "transparency" in image2.info:
                    image2 = image2.convert("RGBA")
                if str(image2.mode) == "RGBA":
                    A2 = image2.getchannel("A")
                else:
                    A2 = None
                if f[0] == "L":
                    channels1 = hsl_split(image, convert=False)
                    channels2 = hsl_split(image2, convert=False)
                else:
                    channels1 = image.convert("HSV").split()
                    channels2 = image2.convert("HSV").split()
                    # channels1 = hsv_split(image, convert=False)
                    # channels2 = hsv_split(image2, convert=False)
                if f == "HUE":
                    channels = [channels2[0], channels1[1], channels1[2]]
                elif f == "SAT":
                    channels = [channels1[0], channels2[1], channels1[2]]
                elif f in ("LUM", "VAL"):
                    channels = [channels1[0], channels1[1], channels2[2]]
                elif f == "COL":
                    channels = [channels2[0], channels2[1], channels1[2]]
                if f[0] == "L":
                    out = hsl_merge(*channels)
                else:
                    out = Image.merge("HSV", channels).convert("RGB")
                    # out = hsv_merge(*channels)
                if A1 or A2:
                    if not A1:
                        A = A2
                    elif not A2:
                        A = A1
                    else:
                        A = ImageMath.eval("max(X,Y)", dict(X=A1, Y=A2)).convert("L")
                    out.putalpha(A)
        elif filt in ("OVERFLOW", "LIGHTING"):
            if str(image.mode) != str(image2.mode):
                if image.mode == "RGBA" or image2.mode == "RGBA":
                    if image.mode != "RGBA":
                        image = image.convert("RGBA")
                    else:
                        image2 = image2.convert("RGBA")
                else:
                    mode = image.mode if image.mode != "P" else "RGBA" if "transparency" in image2.info else "RGB"
                    image2 = image2.convert(mode)
                    if image.mode != mode:
                        image = image.convert(mode)
            image = Image.blend(image, image2, 0.5)
            spl = hsl_split(image, convert=False, dtype=np.uint32)
            if filt == "OVERFLOW":
                spl[-1] <<= 1
            else:
                spl[-1] += (255 ^ spl[-1]) * spl[-1] // 255
            out = hsl_merge(*spl)
        # Otherwise attempt to find as ImageChops filter
        else:
            if str(image.mode) != str(image2.mode):
                if str(image.mode) == "P":
                    image = image.convert("RGBA")
                if str(image.mode) != "RGBA":
                    image = image.convert("RGBA")
                if str(image2.mode) == "P" and "transparency" in image2.info:
                    image2 = image2.convert("RGBA")
                if str(image2.mode) != "RGBA":
                    image2 = image2.convert("RGBA")
            filt = getattr(ImageChops, filt)
            out = filt(image, image2)
        if str(image.mode) != str(out.mode):
            if str(image.mode) == "P":
                image = image.convert("RGBA")
            if str(image.mode) != "RGBA":
                image = image.convert("RGBA")
            if str(out.mode) == "P" and "transparency" in out.info:
                out = out.convert("RGBA")
            if str(out.mode) != "RGBA":
                out = out.convert("RGBA")
        if filt == "blend":
            A = out.getchannel("A")
            A.point(lambda x: round(x * amount))
            out.putalpha(A)
            out = Image.alpha_composite(image, out)
        else:
            if amount == 0:
                out = image
            elif amount != 1:
                out = Image.blend(image, out, amount)
    return out


def remove_matte(image, colour):
    if str(image.mode) == "P":
        image = image.convert("RGBA")
    if str(image.mode) != "RGBA":
        image = image.convert("RGBA")
    arr = np.array(image).astype(np.float32)
    col = np.array(colour)
    t = len(col)
    for row in arr:
        for cell in row:
            r = min(1, np.min(cell[:t] / col))
            if r > 0:
                col = cell[:t] - r * col
                if max(col) > 0:
                    ratio = sum(cell) / max(col)
                    cell[:t] = np.clip(col * ratio, 0, 255)
                    cell[3] /= ratio
                else:
                    cell[3] = 0
    image = fromarray(arr.astype(np.uint8))
    return image


colour_blind_map = dict(
    protan=(
        (
            (0.56667, 0.43333, 0),
            (0.55833, 0.44167, 0),
            (0.24167, 0.75833, 0),
        ),
        (
            (0.81667, 0.18333, 0),
            (0.33333, 0.66667, 0),
            (0, 0.125, 0.875),
        ),
    ),
    deutan=(
        (
            (0.625, 0.375, 0),
            (0.7, 0.3, 0),
            (0, 0.3, 0.7),
        ),
        (
            (0.8, 0.2, 0),
            (0.25833, 0.74167, 0),
            (0, 0.14167, 0.85833),
        ),
    ),
    tritan=(
        (
            (0.95, 0.05, 0),
            (0, 0.43333, 0.56667),
            (0, 0.475, 0.525),
        ),
        (
            (0.96667, 0.03333, 0),
            (0, 0.73333, 0.26667),
            (0, 0.18333, 0.81667),
        ),
    ),
    achro=(
        (
            (0.299, 0.587, 0.114),
            (0.299, 0.587, 0.114),
            (0.299, 0.587, 0.114),
        ),
        (
            (0.618, 0.32, 0.062),
            (0.163, 0.775, 0.062),
            (0.163, 0.32, 0.516),
        ),
    ),
)

colour_normal_map = (
    (1, 0, 0),
    (0, 1, 0),
    (0, 0, 1),
)

def colour_deficiency(image, operation, value=None):
    if value is None:
        if operation == "protanopia":
            operation = "protan"
            value = 1
        elif operation == "protanomaly":
            operation = "protan"
            value = 0.5
        if operation == "deuteranopia":
            operation = "deutan"
            value = 1
        elif operation == "deuteranomaly":
            operation = "deutan"
            value = 0.5
        elif operation == "tritanopia":
            operation = "tritan"
            value = 1
        elif operation == "tritanomaly":
            operation = "tritan"
            value = 0.5
        elif operation in ("monochromacy", "achromatopsia"):
            operation = "achro"
            value = 1
        elif operation == "achromatonomaly":
            operation = "achro"
            value = 0.5
        else:
            value = 1
    try:
        table = colour_blind_map[operation]
    except KeyError:
        raise TypeError(f"Invalid filter {operation}.")
    if value < 0.5:
        value *= 2
        ratios = [table[1][i] * value + colour_normal_map[i] * (1 - value) for i in range(3)]
    else:
        value = value * 2 - 1
        ratios = [table[0][i] * value + table[1][i] * (1 - value) for i in range(3)]
    colourmatrix = []
    for r in ratios:
        colourmatrix.extend(r)
        colourmatrix.append(0)
    if image.mode == "P":
        image = image.convert("RGBA")
    return image.convert(image.mode, colourmatrix)
    channels = list(image.split())
    out = [None] * len(channels)
    if len(out) == 4:
        out[-1] = channels[-1]
    for i_ratio, ratio in enumerate(ratios):
        for i_colour in range(3):
            if ratio[i_colour]:
                im = channels[i_colour].point(lambda x: x * ratio[i_colour])
                if out[i_ratio] is None:
                    out[i_ratio] = im
                else:
                    out[i_ratio] = ImageChops.add(out[i_ratio], im)
    return Image.merge(image.mode, out)

Enhance = lambda image, operation, value: getattr(ImageEnhance, operation)(image).enhance(value)

def brightness(image, value):
    if value:
        if value < 0:
            image = invert(image)
            value = -value
        if str(image.mode) == "P":
            image = image.convert("RGBA")
        if str(image.mode) == "RGBA":
            A = image.getchannel("A")
        else:
            A = None
        H, S, L = hsl_split(image, convert=False, dtype=np.uint32)
        np.multiply(L, value, out=L, casting="unsafe")
        image = hsl_merge(H, S, L)
        if A:
            image.putalpha(A)
    return image

def luminance(image, value):
    if value:
        if value < 0:
            image = invert(image)
            value = -value
        if str(image.mode) == "P":
            image = image.convert("RGBA")
        if str(image.mode) == "RGBA":
            A = image.getchannel("A")
        else:
            A = None
        H, S, L = hcl_split(image, convert=False, dtype=np.float32)
        np.multiply(L, value, out=L, casting="unsafe")
        image = hcl_merge(H, S, L)
        if A:
            image.putalpha(A)
    return image

# Hueshift image using HSV channels
def hue_shift(image, value):
    if value:
        if str(image.mode) == "P":
            image = image.convert("RGBA")
        if str(image.mode) == "RGBA":
            A = image.getchannel("A")
        else:
            A = None
        channels = list(image.convert("HSV").split())
        # channels = hsv_split(image, convert=False)
        # channels[0] += round(value * 256)
        # image = hsv_merge(*channels)
        value *= 256
        channels[0] = channels[0].point(lambda x: (x + value) % 256)
        image = Image.merge("HSV", channels).convert("RGB")
        if A is not None:
            image.putalpha(A)
    return image


# For the ~activity command.
special_colours = {
    "message": (0, 0, 1),
    "typing": (0, 1, 0),
    "command": (0, 1, 1),
    "reaction": (1, 1, 0),
    "misc": (1, 0, 0),
}

def plt_special(d, user=None, **void):
    hours = 336
    plt.style.use("dark_background")
    plt.rcParams["figure.figsize"] = (24, 9)
    plt.rcParams["figure.dpi"] = 96
    plt.xlim(-hours, 0)
    temp = np.zeros(len(next(iter(d.values()))))
    width = hours / len(temp)
    domain = width * np.arange(-len(temp), 0)
    for k, v in d.items():
        plt.bar(domain, v, bottom=temp, color=special_colours.get(k, "k"), edgecolor="white", width=width, label=k)
        temp += np.array(v)
    plt.bar(list(range(-hours, 0)), np.ones(hours) * max(temp) / 512, edgecolor="white", color="k")
    if user:
        plt.title("Recent Discord Activity for " + user)
    plt.xlabel("Time (Hours)")
    plt.ylabel("Action Count")
    plt.legend(loc="upper left")
    ts = time.time_ns() // 1000
    out = f"cache/{ts}.png"
    plt.savefig(out)
    plt.clf()
    return "$" + out

def plt_mp(arr, hours, name):
    if hours >= 336:
        hours /= 24
        if hours >= 336:
            hours /= 30.436849166666665
            if hours >= 24:
                hours /= 12
                word = "years"
            else:
                word = "months"
        else:
            word = "days"
    else:
        word = "hours"
    plt.style.use("dark_background")
    plt.rcParams["figure.figsize"] = (24, 9)
    plt.rcParams["figure.dpi"] = 96
    plt.xlim(-hours, 0)
    x = np.linspace(-hours, 0, len(arr))
    plt.plot(x, arr, "-w")
    plt.xlabel(word.capitalize())
    ts = time.time_ns() // 1000
    out = f"misc/{name}.png"
    plt.savefig(out)
    plt.clf()
    return out

discord_emoji = re.compile("^https?:\\/\\/(?:[a-z]+\\.)?discord(?:app)?\\.com\\/assets\\/[0-9A-Fa-f]+\\.svg")
is_discord_emoji = lambda url: discord_emoji.search(url)


def write_to(fn, data):
    with open(fn, "wb") as f:
        f.write(data)

def write_video(proc, data):
    try:
        i = 0
        while i < len(data):
            proc.stdin.write(data[i:i + 65536])
            i += 65536
        proc.stdin.close()
    except:
        print(traceback.format_exc(), end="")

def from_bytes(b, save=None):
    if b[:4] == b"<svg" or b[:5] == b"<?xml":
        resp = requests.post("https://www.svgtopng.me/api/svgtopng/upload-file", headers=header(), files={"files": ("temp.svg", b, "image/svg+xml"), "format": (None, "PNG"), "forceTransparentWhite": (None, "true"), "jpegQuality": (None, "256")})
        with ZipFile(io.BytesIO(resp.content), compression=zipfile.ZIP_DEFLATED, strict_timestamps=False) as z:
            data = z.read("temp.png")
        out = io.BytesIO(data)
        if save and data and not os.path.exists(save):
            exc.submit(write_to, save, data)
    elif b[:4] == b"%PDF":
        return ImageSequence(*pdf2image.convert_from_bytes(b, poppler_path="misc/poppler", use_pdftocairo=True), copy=True)
    else:
        data = b
        out = io.BytesIO(b) if type(b) is bytes else b
    mime = magic.from_buffer(data)
    if mime == "application/zip":
        z = zipfile.ZipFile(io.BytesIO(data), compression=zipfile.ZIP_DEFLATED, strict_timestamps=False)
        return ImageSequence(*(Image.open(z.open(f.filename)) for f in z.filelist))
    if mime == "image/gif" or mime.split("/", 1)[0] != "image":
        fmt = "rgba" if mime == "image/gif" else "rgb24"
        ts = time.time_ns() // 1000
        fn = "cache/" + str(ts)
        with open(fn, "wb") as f:
            f.write(data)
        cmd = ("ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,avg_frame_rate", "-of", "csv=s=x:p=0", fn)
        print(cmd)
        p = psutil.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        cmd2 = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-an", "-i", fn, "-f", "rawvideo", "-pix_fmt", fmt, "-vsync", "0", "-"]
        print(cmd2)
        proc = psutil.Popen(cmd2, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # exc.submit(write_video, proc, data)
        # p.stdin.write(data)
        # exc.submit(write_video, p, data)
        bcount = 4 if fmt == "rgba" else 3
        mode = "RGBA" if fmt == "rgba" else "RGB"
        try:
            res = as_str(p.stdout.read()).strip()
            if not res:
                raise TypeError(f'Filetype "{mime}" is not supported.')
            info = res.split("x", 2)
        except:
            print(as_str(p.stderr.read()), end="")
            raise
        print(info)
        size = tuple(map(int, info[:2]))
        try:
            duration = 1000 / eval(info[-1], {}, {})
        except (ValueError, TypeError, SyntaxError, ZeroDivisionError):
            duration = 1 / 16
        bcount *= int(np.prod(size))
        images = deque()
        while True:
            b = proc.stdout.read(bcount)
            while len(b) < bcount:
                if not proc.is_running():
                    break
                b += proc.stdout.read(bcount - len(b))
            if len(b) < bcount:
                break
            img = Image.frombuffer(mode, size, b)
            img.info["duration"] = duration
            images.append(img)
        return ImageSequence(*images)
    try:
        return Image.open(out)
    except PIL.UnidentifiedImageError:
        if not b:
            raise FileNotFoundError("image file not found")
        out.seek(0)
        raise TypeError(f'Filetype "{mime}" is not supported.')


def ImageOpIterator(image, step, operation, ts, args):
    # Attempt to perform operation on all individual frames of .gif images
    for i, f in enumerate(range(0, 2147483648, step)):
        np.random.seed(ts & 4294967295)
        globals()["CURRENT_FRAME"] = i
        try:
            image.seek(f)
        except EOFError:
            break
        if str(image.mode) == "P":
            temp = image.convert("RGBA")
        elif str(image.mode) != "RGBA":
            temp = image.convert("RGBA")
        else:
            temp = image
        func = getattr(temp, operation, None)
        if func is None:
            res = eval(operation)(temp, *args)
        else:
            res = func(*args)
        yield res


class ImageSequence(Image.Image):

    def __init__(self, *images, copy=False):
        if copy:
            self._images = [image.copy() for image in images]
        else:
            self._images = images
        self._position = 0

    def seek(self, position):
        if position >= len(self._images):
            raise EOFError
        self._position = position

    def __getattr__(self, key):
        try:
            return self.__getattribute__(key)
        except AttributeError:
            return getattr(self._images[self._position], key)


def get_image(url, out):
    if issubclass(type(url), Image.Image):
        return url
    if type(url) not in (bytes, bytearray, io.BytesIO):
        save = None
        if url in CACHE:
            return CACHE[url]
        if is_url(url):
            data = None
            if is_discord_emoji(url):
                save = f"cache/emoji_{url.rsplit('/', 1)[-1].split('.', 1)[0]}"
                if os.path.exists(save):
                    with open(save, "rb") as f:
                        data = f.read()
                    print(f"Emoji {save} successfully loaded from cache.")
            if data is None:
                data = get_request(url)
            if len(data) > 8589934592:
                raise OverflowError("Max file size to load is 8GB.")
        else:
            if os.path.getsize(url) > 8589934592:
                raise OverflowError("Max file size to load is 8GB.")
            with open(url, "rb") as f:
                data = f.read()
            if out != url and out:
                try:
                    os.remove(url)
                except:
                    pass
        image = from_bytes(data, save)
        CACHE[url] = image
    else:
        if len(url) > 8589934592:
            raise OverflowError("Max file size to load is 8GB.")
        image = from_bytes(url)
    return image


# Main image operation function
@logging
def evalImg(url, operation, args):
    globals()["CURRENT_FRAME"] = 0
    ts = time.time_ns() // 1000
    out = "cache/" + str(ts) + ".png"
    if len(args) > 1 and args[-2] == "-f":
        fmt = args.pop(-1)
        args.pop(-1)
    else:
        fmt = "gif"
    if operation != "$":
        if args and args[-1] == "-raw":
            args.pop(-1)
            image = get_request(url)
        else:
            image = get_image(url, out)
        # -gif is a special case where the output is always a .gif image
        if args and args[-1] == "-gif":
            args.pop(-1)
            if fmt in ("png", "jpg", "jpeg", "bmp"):
                fmt = "gif"
            if fmt == "gif" and np.prod(image.size) > 262144:
                size = max_size(*image.size, 512)
                image = resize_to(image, *size)
            new = eval(operation)(image, *args)
        else:
            try:
                if args and args[0] == "-nogif":
                    args = args[1:]
                    raise EOFError
                image.seek(1)
            except EOFError:
                globals()["ANIM"] = False
                image.seek(0)
                if str(image.mode) == "P":
                    temp = image.convert("RGBA")
                elif str(image.mode) != "RGBA":
                    temp = image.convert("RGBA")
                else:
                    temp = image
                func = getattr(temp, operation, None)
                if func is None:
                    new = eval(operation)(temp, *args)
                else:
                    new = func(*args)
            else:
                new = dict(frames=deque(), duration=0)
                globals()["ANIM"] = True
                for f in range(2147483648):
                    try:
                        image.seek(f)
                    except EOFError:
                        break
                    new["duration"] += max(image.info.get("duration", 0), 1000 / 60)
                fps = 1000 * f / new["duration"]
                step = 1
                while f // step > 4096 and fps // step >= 24:
                    step += 1
                new["count"] = f // step
                new["frames"] = ImageOpIterator(image, step, operation=operation, ts=ts, args=args)
    else:
        new = eval(url)(*args)
    if type(new) is dict:
        duration = new["duration"]
        frames = new["frames"]
        if not frames:
            raise EOFError("No image output detected.")
        elif new["count"] == 1:
            new = next(iter(frames))
        else:
            if fmt in ("png", "jpg", "jpeg", "bmp"):
                fmt = "gif"
            print(duration, new["count"])
            out = "cache/" + str(ts) + "." + fmt
            # if new["count"] <= 1024:
            #     it = iter(frames)
            #     first = next(it)
            #     first.save(out, save_all=True, append_images=it, include_color_table=True, disposal=2, interlace=True, optimize=True, transparency=0, duration=round(1000 * duration / new["count"]), loop=0)
            #     return repr([out])
            fps = 1000 * new["count"] / duration
            if issubclass(type(frames), collections.abc.Sequence):
                first = frames[0]
            else:
                it = iter(frames)
                first = next(it)

                def frameit(first, it):
                    yield first
                    with suppress(StopIteration):
                        while True:
                            yield next(it)

                frames = frameit(first, it)
            mode = str(first.mode)
            if mode == "P":
                mode = "RGBA"
            size = first.size
            if fmt == "zip":
                resp = zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True)
            else:
                command = ["ffmpeg", "-threads", "2", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-framerate", str(fps), "-pix_fmt", ("rgb24" if mode == "RGB" else "rgba"), "-video_size", "x".join(map(str, size)), "-i", "-", "-an"]
                if fmt in ("gif", "webp", "apng"):
                    command.extend(("-gifflags", "-offsetting"))
                    if new["count"] > 4096:
                        vf = None
                        # vf = "split[s0][s1];[s0]palettegen=reserve_transparent=1:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle:alpha_threshold=128"
                    else:
                        vf = "split[s0][s1];[s0]palettegen="
                        if mode == "RGBA":
                            vf += "reserve_transparent=1:"
                        vf += "stats_mode=diff[p];[s1][p]paletteuse=alpha_threshold=128:diff_mode=rectangle"
                    if vf:
                        command.extend(("-vf", vf))
                    command.extend(("-loop", "0"))
                else:
                    meg = round(np.prod(size) * 3 / 1e6, 4)
                    if meg < 1:
                        meg = 1
                    command.extend(("-b:v", f"{meg}M"))
                command.append(out)
                print(command)
                proc = psutil.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for i, frame in enumerate(frames):
                if fmt == "zip":
                    b = io.BytesIO()
                if issubclass(type(frame), Image.Image):
                    if frame.size != size:
                        frame = frame.resize(size)
                    if frame.mode != mode:
                        frame = frame.convert(mode)
                    if fmt == "zip":
                        frame.save(b, "png")
                    else:
                        b = frame.tobytes()
                elif type(frame) is io.BytesIO:
                    if fmt == "zip":
                        with Image.open(frame) as im:
                            im.save(b, "png")
                    else:
                        b = frame.read()
                else:
                    if fmt == "zip":
                        with Image.open(io.BytesIO(frame)) as im:
                            im.save(b, "png")
                    else:
                        b = frame
                if fmt == "zip":
                    b.seek(0)
                    n = len(str(new["count"]))
                    s = f"%0{n}d" % i
                    resp.writestr(f"{s}.png", data=b.read())
                else:
                    proc.stdin.write(b)
                    time.sleep(0.02)
            if fmt == "zip":
                resp.close()
            else:
                proc.stdin.close()
                proc.wait()
            return [out]
    if issubclass(type(new), Image.Image):
        new.save(out, "png")
        return [out]
    elif type(new) is str and new.startswith("$"):
        return [new[1:]]
    return new


def evaluate(ts, args):
    try:
        out = evalImg(*args)
        sys.stdout.buffer.write(f"~PROC_RESP[{ts}].set_result({repr(out)})\n".encode("utf-8"))
    except Exception as ex:
        sys.stdout.buffer.write(f"~PROC_RESP[{ts}].set_exception(evalex({repr(repr(ex))}))\n".encode("utf-8"))
        sys.stdout.buffer.write(f"~print({args},{repr(traceback.format_exc())},sep='\\n',end='')\n".encode("utf-8"))
    sys.stdout.flush()


def ensure_parent(proc, parent):
    while True:
        if not parent.is_running():
            psutil.Process().kill()
        # print(f"~GC.__setitem__({proc.pid}, {len(gc.get_objects())})")
        time.sleep(12)

if __name__ == "__main__":
    pid = os.getpid()
    ppid = os.getppid()
    proc = psutil.Process(pid)
    parent = psutil.Process(ppid)
    exc = concurrent.futures.ThreadPoolExecutor(max_workers=9)
    exc.submit(ensure_parent)
    while True:
        argv = sys.stdin.readline().rstrip()
        if argv:
            if argv[0] == "~":
                ts, s = argv[1:].split("~", 1)
                try:
                    args = eval(literal_eval(s))
                    if "$" in args and "plt_special" in args or "plt_mp" in args:
                        evaluate(ts, args)
                    else:
                        exc.submit(evaluate, ts, args)
                except Exception as ex:
                    sys.stdout.buffer.write(f"~PROC_RESP[{ts}].set_exception(evalex({repr(repr(ex))}))\n".encode("utf-8"))
                    sys.stdout.buffer.write(f"~print({s}, end='')\n".encode("utf-8"))
                    sys.stdout.buffer.write(f"~print({repr(traceback.format_exc())}, end='')\n".encode("utf-8"))
                    sys.stdout.flush()
                while len(CACHE) > 32:
                    try:
                        CACHE.pop(next(iter(CACHE)))
                    except RuntimeError:
                        pass