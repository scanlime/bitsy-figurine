#!/usr/bin/env python3
#
# Make figurines from Bitsy sprites
# - Micah Scott 2018
#

from html.parser import HTMLParser
import subprocess, multiprocessing
import sys, os, re, math

openscad_template = '''// %(tag)r
// pixels=%(num_pixels)d supports=%(num_supports)d

displayname = %(displayname)s;
custom_text_1 = %(custom_text_1)s;
custom_text_2 = %(custom_text_2)s;

unit = 4;

base_thick = 2.8;
base_border = 11;
base_round = 5;

support_width = unit;
support_thickness = unit / 3;

label_size = 4;
label_font_top = "Consolas:style=Bold";
label_font_bottom = "Consolas";
label_depth = 0.3;
label_margin = 2;

pixel_round = 1.0;
pixel_glue = 1.0;

epsilon = 0.001;
minimum_text_margin = 0.5;
$fn = 8;

base_width = (%(xmax)d-%(xmin)d+1)*unit + 2*base_border;
base_height = unit + base_border;

// Entire figurine
rotate([0, 0, 20])
union() {

    // Base
    translate([%(xmin)d*unit-base_border, -base_thick - pixel_glue + epsilon, unit + base_border])
    rotate([-90, 0, 0])

    difference() {
        union() {
            $fn = 40;

            // Rounded pedestal
            linear_extrude(height=base_thick)
            offset(r=base_round)
            offset(delta=-base_round)
            square(size=[base_width, base_height]);

            // Raised text on topside
            translate([0, 0, base_thick - label_depth])
            linear_extrude(height=label_depth*2)
            intersection() {
                translate([label_margin, label_margin + label_size * 0.25])
                    text(text=displayname, size=label_size, font=label_font_top);
                square(size=[base_width - minimum_text_margin, base_height]);
            }
        }

        // Sunken text on underside
        translate([label_margin, label_margin + label_size, label_depth])
        rotate([180, 0, 0])
        linear_extrude(height=label_depth*2)
        union() {
            text(text=custom_text_1, size=label_size, font=label_font_bottom);
            translate([0, label_size * -1.6])
                text(text=custom_text_2, size=label_size, font=label_font_bottom);
        }
    }

    // Pixel cubes with a bit of round offset
    linear_extrude(height=unit)
    offset(r=pixel_round)
    offset(delta=-pixel_round)
    union()
    {
%(pixels)s
    }

    // Support posts
    linear_extrude(height=support_thickness)
    translate([unit/2 - support_width/2, -pixel_glue - epsilon])
    union()
    {
%(supports)s
    }
}
'''

openscad_pixel = (' '*8 +
    'translate([%s*unit, %s*unit]) offset(delta=pixel_glue) ' +
    'square(size=unit);')

openscad_support = (' '*8 +
    'translate([%s*unit, 0]) ' +
    'square(size=[support_width, %s*unit + pixel_glue*3]);')

def openscad_str(s):
    return 'str(%s)' % ','.join('chr(%s)' % ord(c) for c in s)

def move_reachable_pixels(from_set, to_set, xy):
    if xy in from_set:
        from_set.remove(xy)
        to_set.add(xy)
    x, y = xy
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            nxy = (x + dx, y + dy)
            if nxy in from_set:
                move_reachable_pixels(from_set, to_set, nxy)


class Figurine:
    def __init__(self, image, custom_text='', name_simplify_re=None):
        self.image = image
        self.custom_text = custom_text
        self.name_simplify_re = name_simplify_re

    def _filename_for_string(self, s, ext=''):
        s = re.subn('[^a-zA-Z0-9\.\-_]', '_', s)[0]
        s = re.subn('_+', '_', s)[0]
        return s + ext

    def iter_supports(self):
        # At first assume all pixels are unsupported
        unsupported = set()
        for xy in self.image.iter_pixels():
            unsupported.add(xy)

        # Support at the base
        supported_by_base = set()
        for x in range(8):
            move_reachable_pixels(unsupported, supported_by_base, (x, -1))

        # For each remaining unsupported pixel, find all adjoining
        while unsupported:
            xy = unsupported.pop()
            group = set()
            group.add(xy)
            move_reachable_pixels(unsupported, group, xy)
            # Find the lowest row
            lowest_y = min(y for (x, y) in group)
            # X for center of mass
            center_x = sum(x for (x, y) in group) / len(group)
            # X points on that bottom row
            lowest_x_list = [x for (x, y) in group if y == lowest_y]
            # If the center is under two pixels, we can place it at the proper
            # location between them. Otherwise we pick the center of the closest
            # pixel.
            if (int(center_x) in lowest_x_list) and (int(center_x + 1) in lowest_x_list):
                yield (center_x, lowest_y)
            else:
                distances = [(abs(center_x - x), x) for x in lowest_x_list]
                distances.sort()
                yield (distances[0][1], lowest_y)

    @property
    def tag(self):
        if self.custom_text:
            return '%s_%s' % (self.image.tag, self.custom_text)
        else:
            return self.image.tag

    @property
    def displayname(self):
        if self.name_simplify_re:
            return re.subn(self.name_simplify_re, '', self.image.name, flags=re.IGNORECASE)[0]
        else:
            return self.image.name

    @property
    def scad_filename(self):
        return self._filename_for_string(self.tag, '.scad')

    @property
    def stl_filename(self):
        return self._filename_for_string(self.tag, '.stl')

    @property
    def png_filename(self):
        # Use image tag only; customization is not visible
        return self._filename_for_string(self.image.tag, '.png')

    @property
    def openscad_code(self):
        pixels = [openscad_pixel % xy for xy in self.image.iter_pixels()]
        supports = [openscad_support % xy for xy in self.iter_supports()]
        xrange = self.image.xrange
        custom_text_lines = (self.custom_text + '\n\n').split('\n')
        return openscad_template % dict(
            xmin = xrange[0],
            xmax = xrange[1],
            pixels = '\n'.join(pixels),
            supports = '\n'.join(supports),
            num_pixels = len(pixels),
            num_supports = len(supports),
            displayname = openscad_str(self.displayname),
            custom_text_1 = openscad_str(custom_text_lines[0]),
            custom_text_2 = openscad_str(custom_text_lines[1]),
            tag = self.tag)

    def write_openscad(self, output_path='.'):
        path = os.path.join(output_path, self.scad_filename)
        code = self.openscad_code.encode('utf8')
        with open(path, 'wb') as f:
            f.write(code)
            f.close()
        return path

    def write_stl(self, output_path='.', openscad_exe='openscad'):
        scad = self.write_openscad(output_path)
        stl = os.path.join(output_path, self.stl_filename)
        subprocess.run([ openscad_exe, '-o', stl, scad ], stdout=subprocess.DEVNULL)
        return stl

    def write_png(self, output_path='.', openscad_exe='openscad', size=(800, 800)):
        scad = self.write_openscad(output_path)
        png = os.path.join(output_path, self.png_filename)
        subprocess.run([ openscad_exe, '-o', png, scad,
            '--imgsize=%d,%d' % size,
            '--camera=10,15,0,-20,10,20,145'
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return png


class BitsyImage:
    def __init__(self, lines, name, index, ident, blocktype):
        self.lines = lines
        self.name = name
        self.index = index
        self.ident = ident
        self.blocktype = blocktype
        self.tag = '%s_%s.%s.%d' % (name, blocktype, ident, index)

    def iter_pixels(self):
        for y, (line,) in enumerate(reversed(self.lines)):
            for x, pixel in enumerate(line):
                if pixel == '1':
                    yield (x, y)

    @property
    def xrange(self):
        xrange = None
        for (x, y) in self.iter_pixels():
            if xrange:
                xrange = (min(xrange[0], x), max(xrange[1], x))
            else:
                xrange = (x, x)
        if xrange:
            return xrange
        else:
            return (0, 0)


class BitsyHTMLParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self._tag = None
        self._attrs = None
        self.images = []

    def handle_starttag(self, tag, attrs):
        self._tag = tag
        self._attrs = attrs

    def handle_endtag(self, tag):
        self._tag = None
        self._attrs = None

    def handle_data(self, data):
        if self._tag == 'script' and ('id', 'exportedGameData') in self._attrs:
            self.handle_gamedata(data)

    def handle_gamedata(self, data):
        quoted = False
        block = []
        for line in data.split('\n'):
            line = line.strip()
            if line == '"""':
                quoted = not quoted
            elif not line and not quoted:
                # Unquoted blank lines end the block
                if block:
                    self.handle_game_block(block)
                block = []
            else:
                block.append(line.split())

    def handle_game_block(self, block):
        fn = getattr(self, 'handle_%s' % block[0][0], None)
        if fn:
            fn(block)

    def handle_TIL(self, block):
        self.handle_visual_block(block, 'tile')

    def handle_SPR(self, block):
        self.handle_visual_block(block, 'sprite')

    def handle_visual_block(self, block, blocktype):
        ident = block[0][1]
        name = ''
        images = [[]]

        for line in block[1:]:
            if line[0] == 'NAME':
                name = line[1]
            elif line[0] == '>':
                images.append([])
            elif len(line[0]) == 8:
                images[-1].append(line)

        for i, image in enumerate(images):
            assert len(image) == 8
            self.images.append(BitsyImage(image, name, i, ident, blocktype))


def visit_image(image):
    fig = Figurine(image)
    fig.write_png('output')
    stl = fig.write_stl('output')
    print(stl)


def filter_test(filters, image):
    tag = image.tag
    if not filters:
        return True
    for f in filters:
        if tag.find(f) >= 0:
            return True
    return False


def main():
    if len(sys.argv) >= 2:
        with open(sys.argv[1], 'rb') as f:
            filter = sys.argv[2:]
            parser = BitsyHTMLParser()
            parser.feed(f.read().decode('utf8', 'replace'))

            images = []
            for image in parser.images:
                if filter_test(filter, image):
                    print(image.tag)
                    images.append(image)

            multiprocessing.Pool().map(visit_image, images)
    else:
        print('usage: %s index.html [filter]' % sys.argv[0])

if __name__ == '__main__':
    main()
