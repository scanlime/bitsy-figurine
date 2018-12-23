#!/usr/bin/env python3
#
# Make figurines from Bitsy sprites
# - Micah Scott 2018
#

from html.parser import HTMLParser
import subprocess
import sys
import os

openscad = 'C:/Program Files/OpenSCAD/openscad.exe'
output_path = 'output'

class BitsyHTMLParser(HTMLParser):
    _tag = None
    _attrs = None

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

    def handle_SPR(self, block):
        ident = block[0][1]
        name = ''
        images = [[]]

        for line in block[1:]:
            if line[0] == 'NAME':
                name = line[1].replace('?','')
            elif line[0] == '>':
                images.append([])
            elif len(line[0]) == 8:
                images[-1].append(line)

        for i, image in enumerate(images):
            assert len(image) == 8
            self.handle_SPR_image(ident, name, i, image)

    def handle_SPR_image(self, ident, name, index, image):
        pixels = ''
        xrange = None
        for y, (line,) in enumerate(reversed(image)):
            for x, pixel in enumerate(line):
                if pixel == '1':
                    pixels += (
                        ('translate([%d*unit, %d*unit]) ' % (x, y))
                        + 'offset(delta=pixel_glue) '
                        + 'square(size=unit);\n')
                    if xrange:
                        xrange = (min(xrange[0], x), max(xrange[1], x))
                    else:
                        xrange = (x, x)
        if not xrange:
            return
        xmin, xmax = xrange
        tag = 'sprite_%s_%s_%d' % (ident, name, index)
        scad_file = os.path.join(output_path, tag + '.scad')
        stl_file = os.path.join(output_path, tag + '.stl')
        print(tag)

        with open(scad_file, 'w') as f:
            f.write('''// sprite %(ident)s %(name)r #%(index)d

unit = 4;

base_thick = 2.5;
base_border = 12;
base_round = 5;
label_size = 4;
label_font = "Consolas";
label_depth = 0.4;
label_margin = 2;

pixel_round = 1.0;
pixel_glue = 1.0;

epsilon = 0.001;
$fn = 16;

// Entire figurine
union() {

    // Base
    translate([%(xmin)d*unit-base_border, -base_thick - pixel_glue + epsilon, unit + base_border])
    rotate([-90, 0, 0])
    difference() {

        // Rounded pedestal
        linear_extrude(height=base_thick)
        offset(r=base_round)
        offset(delta=-base_round)
        square(size=[(%(xmax)d-%(xmin)d+1)*unit + 2*base_border, unit + base_border]);

        // Text
        translate([label_margin, label_margin, base_thick - label_depth])
        linear_extrude(height=label_depth*2)
        text(text="%(name)s", size=label_size, font=label_font);
    }

    // Pixel cubes with a bit of round offset
    linear_extrude(height=unit)
    offset(r=pixel_round)
    offset(delta=-pixel_round)
    union()
    {
        // 2D pixel squares
        %(pixels)s
    }
}
''' % locals())
            f.close()
        subprocess.run([ openscad, '-o', stl_file, scad_file ], check=True)

if len(sys.argv) == 2:
    with open(sys.argv[1], 'rb') as f:
        BitsyHTMLParser().feed(f.read().decode('utf8', 'replace'))
else:
    print('usage: %s index.html' % sys.argv[0])
