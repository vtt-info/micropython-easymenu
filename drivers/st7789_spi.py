# 适用于 ST7789 的 SPI 直接驱动
# Github: https://github.com/funnygeeker/micropython-easydisplay
# Author: funnygeeker
# Licence: MIT
# Date: 2023/11/30
#
# 参考资料:
# https://github.com/russhughes/st7789py_mpy/
# https://github.com/AntonVanke/MicroPython-uFont
# https://github.com/cheungbx/st7735-esp8266-micropython/blob/master/st7735.py
import math
from struct import pack
from machine import Pin, PWM
from micropython import const
from time import sleep_us, sleep_ms

# commands
ST7789_NOP = const(0x00)
ST7789_SWRESET = const(0x01)
ST7789_RDDID = const(0x04)
ST7789_RDDST = const(0x09)

ST7789_SLPIN = const(0x10)
ST7789_SLPOUT = const(0x11)
ST7789_PTLON = const(0x12)
ST7789_NORON = const(0x13)

ST7789_INVOFF = const(0x20)
ST7789_INVON = const(0x21)
ST7789_DISPOFF = const(0x28)
ST7789_DISPON = const(0x29)
ST7789_CASET = const(0x2A)
ST7789_RASET = const(0x2B)
ST7789_RAMWR = const(0x2C)
ST7789_RAMRD = const(0x2E)

ST7789_PTLAR = const(0x30)
ST7789_VSCRDEF = const(0x33)
ST7789_COLMOD = const(0x3A)
ST7789_MADCTL = const(0x36)
ST7789_VSCSAD = const(0x37)

ST7789_MADCTL_MY = const(0x80)
ST7789_MADCTL_MX = const(0x40)
ST7789_MADCTL_MV = const(0x20)
ST7789_MADCTL_ML = const(0x10)
ST7789_MADCTL_BGR = const(0x08)
ST7789_MADCTL_MH = const(0x04)
ST7789_MADCTL_RGB = const(0x00)

ST7789_RDID1 = const(0xDA)
ST7789_RDID2 = const(0xDB)
ST7789_RDID3 = const(0xDC)
ST7789_RDID4 = const(0xDD)

COLOR_MODE_65K = const(0x50)
COLOR_MODE_262K = const(0x60)
COLOR_MODE_12BIT = const(0x03)
COLOR_MODE_16BIT = const(0x05)
COLOR_MODE_18BIT = const(0x06)
COLOR_MODE_16M = const(0x07)
#
FRMCTR1 = const(0xB1)
FRMCTR2 = const(0xB2)
FRMCTR3 = const(0xB3)

INVCTR = const(0xB4)

PWCTR1 = const(0xC0)
PWCTR2 = const(0xC1)
PWCTR3 = const(0xC2)
PWCTR4 = const(0xC3)
PWCTR5 = const(0xC4)
VMCTR1 = const(0xC5)

# Color definitions
BLACK = const(0x0000)
BLUE = const(0x001F)
RED = const(0xF800)
GREEN = const(0x07E0)
CYAN = const(0x07FF)
MAGENTA = const(0xF81F)
YELLOW = const(0xFFE0)
WHITE = const(0xFFFF)

_ENCODE_PIXEL = ">H"
_ENCODE_POS = ">HH"
_DECODE_PIXEL = ">BBB"

_BUFFER_SIZE = const(256)

_BIT7 = const(0x80)
_BIT6 = const(0x40)
_BIT5 = const(0x20)
_BIT4 = const(0x10)
_BIT3 = const(0x08)
_BIT2 = const(0x04)
_BIT1 = const(0x02)
_BIT0 = const(0x01)

# Rotation tables (width, height, xstart, ystart)

WIDTH_320 = [(240, 320, 0, 0),
             (320, 240, 0, 0),
             (240, 320, 0, 0),
             (320, 240, 0, 0),
             (240, 320, 0, 0),
             (320, 240, 0, 0),
             (240, 320, 0, 0)]  # 320x240
WIDTH_240 = [(240, 240, 0, 0),
             (240, 240, 0, 0),
             (240, 240, 80, 0),
             (240, 240, 0, 80),
             (240, 240, 0, 0),
             (240, 240, 0, 0),
             (240, 240, 80, 0)]  # 240x240
WIDTH_135 = [(135, 240, 52, 40),
             (240, 135, 40, 53),
             (135, 240, 53, 40),
             (240, 135, 40, 52),
             (135, 240, 52, 40),
             (240, 135, 40, 53),
             (135, 240, 53, 40)]  # 135x240
# on MADCTL to control display rotation/color layout
# Looking at display with pins on top.
# 00 = upper left printing right
# 10 = does nothing (MADCTL_ML)
# 40 = upper right printing left (backwards) (X Flip)
# 20 = upper left printing down (backwards) (Vertical flip)
# 80 = lower left printing right (backwards) (Y Flip)
# 04 = (MADCTL_MH)

# 60 = 90 right rotation
# C0 = 180 right rotation
# A0 = 270 right rotation
ROTATIONS = [0x00, 0x60, 0xC0, 0xA0, 0x40, 0x20, 0x80]  # 旋转方向


def _encode_pos(x, y):
    """Encode a postion into bytes."""
    return pack(_ENCODE_POS, x, y)


def _encode_pixel(c):
    """Encode a pixel color into bytes."""
    return pack(_ENCODE_PIXEL, c)


class ST7789:
    def __init__(self, width: int, height: int, spi, rst: int, dc: int,
                 cs: int = None, bl: int = None, rotate: int = 0, rgb=True, invert: bool = True):
        """
        初始化屏幕驱动

        Args:
            width: 宽度
            height: 高度
            spi: SPI 实例
            rst: RESET 引脚
            dc: Data / Command 引脚
            cs: 片选引脚
            bl: 背光引脚
            rotate: 旋转图像，数值为 0-6
            rgb: 使用 RGB 颜色模式，而不是 BGR
            invert: 反转颜色
        """
        self.width = width
        self.height = height
        self.x_start = 0
        self.y_start = 0
        self.spi = spi
        self.rst = Pin(rst, Pin.OUT, Pin.PULL_DOWN)
        self.dc = Pin(dc, Pin.OUT, Pin.PULL_DOWN)
        if cs is None:
            self.cs = int
        else:
            self.cs = Pin(cs, Pin.OUT, Pin.PULL_DOWN)
        if bl is not None:
            self.bl = PWM(Pin(bl, Pin.OUT))
            self.bl.duty(1023)
        else:
            self.bl = None
        self._rotate = rotate
        self._rgb = rgb
        self.hard_reset()
        self.soft_reset()
        self.poweron()
        #
        sleep_us(300)
        self._write(FRMCTR1, bytearray([0x01, 0x2C, 0x2D]))
        self._write(FRMCTR2, bytearray([0x01, 0x2C, 0x2D]))
        self._write(FRMCTR3, bytearray([0x01, 0x2C, 0x2D, 0x01, 0x2C, 0x2D]))
        sleep_us(10)
        self._write(INVCTR, bytearray([0x07]))
        self._write(PWCTR1, bytearray([0xA2, 0x02, 0x84]))
        self._write(PWCTR2, bytearray([0xC5]))
        self._write(PWCTR3, bytearray([0x0A, 0x00]))
        self._write(PWCTR4, bytearray([0x8A, 0x2A]))
        self._write(PWCTR5, bytearray([0x8A, 0xEE]))
        self._write(VMCTR1, bytearray([0x0E]))
        #
        self._set_color_mode(COLOR_MODE_65K | COLOR_MODE_16BIT)
        sleep_ms(50)
        self.rotate(self._rotate)
        self.invert(invert)
        sleep_ms(10)
        self._write(ST7789_NORON)
        sleep_ms(10)
        self._write(ST7789_DISPON)
        sleep_ms(100)
        self.clear()

    def _write(self, command=None, data=None):
        """SPI write to the device: commands and data."""
        self.cs(0)
        if command is not None:
            self.dc(0)
            self.spi.write(bytes([command]))
        if data is not None:
            self.dc(1)
            self.spi.write(data)
        self.cs(1)

    def write_cmd(self, cmd):
        """
        写命令

        Args:
            cmd: 命令内容
        """
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([cmd]))
        self.cs(1)

    def write_data(self, data):
        """
        写数据

        Args:
            data: 数据内容
        """
        self.cs(0)
        self.dc(1)
        self.spi.write(data)
        self.cs(1)

    def hard_reset(self):
        """
        Hard reset display.
        """
        self.cs(0)
        self.rst(1)
        sleep_ms(50)
        self.rst(0)
        sleep_ms(50)
        self.rst(1)
        sleep_ms(150)
        self.cs(1)

    def soft_reset(self):
        """
        Soft reset display.
        """
        self._write(ST7789_SWRESET)
        sleep_ms(150)

    def poweron(self):
        """Disable display sleep mode."""
        self._write(ST7789_SLPOUT)

    def poweroff(self):
        """Enable display sleep mode."""
        self._write(ST7789_SLPIN)

    def invert(self, value):
        """
        Enable or disable display inversion mode.

        Args:
            value (bool): if True enable inversion mode. if False disable
            inversion mode
        """
        if value:
            self._write(ST7789_INVON)
        else:
            self._write(ST7789_INVOFF)

    def _set_color_mode(self, mode):
        """
        Set display color mode.

        Args:
            mode (int): color mode
                COLOR_MODE_65K, COLOR_MODE_262K, COLOR_MODE_12BIT,
                COLOR_MODE_16BIT, COLOR_MODE_18BIT, COLOR_MODE_16M
        """
        self._write(ST7789_COLMOD, bytes([mode & 0x77]))

    def rotate(self, rotate):
        """
        Set display rotation.

        Args:
            rotate (int):
                - 0-Portrait
                - 1-Landscape
                - 2-Inverted Portrait
                - 3-Inverted Landscape
                - 4-Upper right printing left (backwards) (X Flip)
                - 5-Upper left printing down (backwards) (Vertical flip)
                - 6-Lower left printing right (backwards) (Y Flip)
        """
        self._rotate = rotate
        madctl = ROTATIONS[rotate]
        if self.width == 320:
            table = WIDTH_320
        elif self.width == 240:
            table = WIDTH_240
        elif self.width == 135:
            table = WIDTH_135
        else:
            raise ValueError(
                "Unsupported display. 320x240, 240x240 and 135x240 are supported."
            )

        self.width, self.height, self.x_start, self.y_start = table[rotate]
        self._write(ST7789_MADCTL, bytes([madctl | 0x00 if self._rgb else 0x08]))

    def _set_columns(self, start, end):
        """
        Send CASET (column address set) command to display.

        Args:
            start (int): column start address
            end (int): column end address
        """
        if start <= end <= self.width:
            self._write(ST7789_CASET, _encode_pos(
                start + self.x_start, end + self.x_start))

    def _set_rows(self, start, end):
        """
        Send RASET (row address set) command to display.

        Args:
            start (int): row start address
            end (int): row end address
       """
        if start <= end <= self.height:
            self._write(ST7789_RASET, _encode_pos(
                start + self.y_start, end + self.y_start))

    def set_window(self, x0, y0, x1, y1):
        """
        Set window to column and row address.

        Args:
            x0 (int): column start address
            y0 (int): row start address
            x1 (int): column end address
            y1 (int): row end address
        """
        if x0 < self.width and y0 < self.height:
            self._set_columns(x0, x1)
            self._set_rows(y0, y1)
            self._write(ST7789_RAMWR)

    def clear(self):
        """
        清屏
        """
        self.fill(0)

    def show(self):
        """
        将帧缓冲区数据发送到屏幕
        """
        pass  # 无帧缓冲区

    def rgb(self, enable: bool):
        """
        设置颜色模式

        Args:
            enable: RGB else BGR
        """
        self._rgb = enable
        self._write(ST7789_MADCTL, bytes([ROTATIONS[self._rotate] | 0x00 if self._rgb else 0x08]))

    @staticmethod
    def color(r, g, b):
        """
        Convert red, green and blue values (0-255) into a 16-bit 565 encoding.
        """
        return (r & 0xf8) << 8 | (g & 0xfc) << 3 | b >> 3

    def back_light(self, value):
        """
        背光调节

        Args:
            value: 背光等级 0 ~ 255
        """
        self.bl.freq(1000)
        if value >= 0xff:
            value = 0xff
        data = value * 0xffff >> 8
        self.bl.duty_u16(data)

    def vline(self, x, y, h, c):
        """
        Draw vertical line at the given location and color.

        Args:
            x (int): x coordinate
            y (int): y coordinate
            h (int): length of line
            c (int): 565 encoded color
        """
        self.fill_rect(x, y, 1, h, c)

    def hline(self, x, y, w, c):
        """
        Draw horizontal line at the given location and color.

        Args:
            x (int): x coordinate
            y (int): y coordinate
            w (int): length of line
            c (int): 565 encoded color
        """
        self.fill_rect(x, y, w, 1, c)

    def pixel(self, x, y, c: int = None):
        """
        Draw a pixel at the given location and color.

        Args:
            x (int): x coordinate
            y (int): y coordinate
            c (int): 565 encoded color
        """
        self.set_window(x, y, x, y)
        self._write(None, _encode_pixel(c))

    def blit_buffer(self, buffer, x, y, width, height):
        """
        Copy buffer to display at the given location.

        Args:
            buffer (bytes): Data to copy to display
            x (int): Top left corner x coordinate
            y (int): Top left corner y coordinate
            width (int): Width
            height (int): Height
        """
        self.set_window(x, y, x + width - 1, y + height - 1)
        self._write(None, buffer)

    def rect(self, x, y, w, h, c):
        """
        Draw a rectangle at the given location, size and color.

        Args:
            x (int): Top left corner x coordinate
            y (int): Top left corner y coordinate
            w (int): Width in pixels
            h (int): Height in pixels
            c (int): 565 encoded color
        """
        self.hline(x, y, w, c)
        self.vline(x, y, h, c)
        self.vline(x + w - 1, y, h, c)
        self.hline(x, y + h - 1, w, c)

    def fill_rect(self, x, y, w, h, c):
        """
        Draw a rectangle at the given location, size and filled with color.

        Args:
            x (int): Top left corner x coordinate
            y (int): Top left corner y coordinate
            w (int): Width in pixels
            h (int): Height in pixels
            c (int): 565 encoded color
        """
        self.set_window(x, y, x + w - 1, y + h - 1)
        chunks, rest = divmod(w * h, _BUFFER_SIZE)
        pixel = _encode_pixel(c)
        self.dc(1)
        if chunks:
            data = pixel * _BUFFER_SIZE
            for _ in range(chunks):
                self._write(None, data)
        if rest:
            self._write(None, pixel * rest)

    def fill(self, c):
        """
        Fill the entire FrameBuffer with the specified color.

        Args:
            c (int): 565 encoded color
        """
        self.fill_rect(0, 0, self.width, self.height, c)

    def line(self, x1, y1, x2, y2, c):
        """
        Draw a single pixel wide line starting at x0, y0 and ending at x1, y1.

        Args:
            x1 (int): Start point x coordinate
            y1 (int): Start point y coordinate
            x2 (int): End point x coordinate
            y2 (int): End point y coordinate
            c (int): 565 encoded color
        """
        steep = abs(y2 - y1) > abs(x2 - x1)
        if steep:
            x1, y1 = y1, x1
            x2, y2 = y2, x2
        if x1 > x2:
            x1, x2 = x2, x1
            y1, y2 = y2, y1
        dx = x2 - x1
        dy = abs(y2 - y1)
        err = dx // 2
        ystep = 1 if y1 < y2 else -1
        while x1 <= x2:
            if steep:
                self.pixel(y1, x1, c)
            else:
                self.pixel(x1, y1, c)
            err -= dy
            if err < 0:
                y1 += ystep
                err += dx
            x1 += 1

    def circle(self, center, radius, c, section=100):
        """
        画圆

        Args:
            c: 颜色
            center: 中心(x, y)
            radius: 半径
            section: 分段
        """
        arr = []
        for m in range(section + 1):
            x = round(radius * math.cos((2 * math.pi / section) * m - math.pi) + center[0])
            y = round(radius * math.sin((2 * math.pi / section) * m - math.pi) + center[1])
            arr.append([x, y])
        for i in range(len(arr) - 1):
            self.line(*arr[i], *arr[i + 1], c)

    def fill_circle(self, center, radius, c):
        """
        画填充圆

        Args:
            c: 颜色
            center: 中心(x, y)
            radius: 半径
        """
        rsq = radius * radius
        for x in range(radius):
            y = int(math.sqrt(rsq - x * x))  # 计算 y 坐标
            y0 = center[1] - y
            end_y = y0 + y * 2
            y0 = max(0, min(y0, self.height))  # 将 y0 限制在画布的范围内
            length = abs(end_y - y0) + 1
            self.vline(center[0] + x, y0, length, c)  # 绘制左右两侧的垂直线
            self.vline(center[0] - x, y0, length, c)

    # def image(self, file_name):
    #     with open(file_name, "rb") as bmp:
    #         for b in range(0, 80 * 160 * 2, 1024):
    #             self.buffer[b:b + 1024] = bmp.read(1024)
    #         self.show()
