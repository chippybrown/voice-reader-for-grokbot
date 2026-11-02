# Write the Windows version resource PyInstaller embeds in the exe.
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import version  # noqa: E402


def main(path):
    parts = [int(piece) for piece in version.VERSION.split(".")]
    while len(parts) < 4:
        parts.append(0)
    filevers = "(%s)" % ", ".join(str(part) for part in parts[:4])
    text = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=%s,
    prodvers=%s,
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
        StringStruct('CompanyName', 'Grokbot Voice'),
        StringStruct('FileDescription', 'Grokbot Voice'),
        StringStruct('FileVersion', '%s'),
        StringStruct('InternalName', 'GrokbotVoice'),
        StringStruct('OriginalFilename', 'Grokbot.Voice.exe'),
        StringStruct('ProductName', 'Grokbot Voice'),
        StringStruct('ProductVersion', '%s')
        ])
      ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""" % (filevers, filevers, version.VERSION, version.VERSION)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    with open(os.path.join(os.path.dirname(path), "version.txt"), "w", encoding="utf-8") as handle:
        handle.write(version.VERSION + "\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join("dist", "version-info.txt"))
