import sys, os, subprocess, traceback
from traceback import print_exc

# Required to open python on different operating systems
python = sys.executable


if sys.version_info[0] < 3:
    raise ImportError("Python 3 required.")

print("Loading and checking modules...")

with open("requirements.txt", "rb") as f:
    modlist = f.read().decode("utf-8", "replace").replace("\r", "\n").split("\n")

try:
    import pkg_resources
except:
    print_exc()
    subprocess.run(["pip", "install", "setuptools", "--upgrade", "--user"])
    import pkg_resources
x = sys.version_info[1]

installing = []
install = lambda m: installing.append(subprocess.Popen([python, "-m", "pip", "install", m, "--upgrade", "--user"]))

# Parse requirements.txt
for mod in modlist:
    if mod:
        try:
            name = mod
            version = None
            for op in (">=", "==", "<="):
                if op in mod:
                    name, version = mod.split(op)
                    break
            v = pkg_resources.get_distribution(name).version
            if version is not None:
                s = repr(v) + op + repr(version)
                assert eval(s, {}, {})
        except:
            # Modules may require an older version, replace current version if necessary
            print_exc()
            inst = name
            if op in ("==", "<="):
                inst += "==" + version
            install(inst)

# Run pip on any modules that need installing
if installing:
    print("Installing missing or outdated modules, please wait...")
    subprocess.run([python, "-m", "pip", "install", "pip", "--upgrade", "--user"])
    for i in installing:
        i.wait()
try:
    pkg_resources.get_distribution("colorspace")
except pkg_resources.DistributionNotFound:
    subprocess.run([python, "-m", "pip", "install", "git+https://github.com/retostauffer/python-colorspace", "--user"])
print("Installer terminated.")