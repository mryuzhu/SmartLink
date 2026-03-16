from __future__ import annotations

import webbrowser

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    pystray = None
    Image = None
    ImageDraw = None
    ImageFont = None


def tray_available() -> bool:
    return pystray is not None and Image is not None


def build_icon():
    image = Image.new("RGBA", (32, 32), (22, 110, 227, 255))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    text = "SL"
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    draw.text(((32 - width) // 2, (32 - height) // 2), text, fill=(255, 255, 255), font=font)
    return image


class TrayManager:
    def __init__(self, dashboard_url: str, mobile_url: str, on_exit) -> None:
        self.dashboard_url = dashboard_url
        self.mobile_url = mobile_url
        self.on_exit = on_exit

    def run(self) -> None:  # pragma: no cover
        if not tray_available():
            raise RuntimeError("pystray/pillow 不可用")

        def open_dashboard(_icon, _item):
            webbrowser.open(self.dashboard_url)

        def open_mobile(_icon, _item):
            webbrowser.open(self.mobile_url)

        def exit_app(icon, _item):
            icon.stop()
            self.on_exit()

        menu = pystray.Menu(
            pystray.MenuItem("打开控制台", open_dashboard),
            pystray.MenuItem("打开手机页", open_mobile),
            pystray.MenuItem("退出 SmartLink", exit_app),
        )
        icon = pystray.Icon("SmartLink", build_icon(), "SmartLink 运行中", menu)
        icon.run()
