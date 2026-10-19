"""Check rendered PNG chart pixels without modifying any image."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    report = {'checks': [], 'passed': False, 'scope': 'nonblank chart colors and hover pixel changes; numeric accuracy verified separately by API/UI tests'}
    files = sorted(p for p in args.directory.glob('chart-*.png') if not p.name.startswith('chart-hover-'))
    assert files, 'No chart screenshots found'
    for filename in files:
        with Image.open(filename) as source:
            img = source.convert('RGB')
        colors = img.getcolors(img.width * img.height)
        teal_pixels = sum(n for n, (r, g, b) in colors if g > r + 25 and b > r + 20)
        distinct = len(colors)
        assert img.width >= 250 and img.height >= 300, (filename, img.size)
        assert teal_pixels > 150 and distinct > 40, (filename, teal_pixels, distinct)
        check = {'file': filename.name, 'width': img.width, 'height': img.height,
                 'teal_pixels': teal_pixels, 'distinct_colors': distinct,
                 'sha256': hashlib.sha256(filename.read_bytes()).hexdigest()}
        hover = filename.with_name(filename.name.replace('chart-', 'chart-hover-', 1))
        if hover.exists():
            with Image.open(hover) as source:
                changed = ImageChops.difference(img, source.convert('RGB'))
            changed_pixels = sum(n for n, color in changed.getcolors(img.width * img.height)
                                 if max(color) > 15)
            assert changed_pixels > 200, (filename, 'hover did not visibly change chart', changed_pixels)
            check['hover_changed_pixels'] = changed_pixels
        report['checks'].append(check)
    report['passed'] = True
    (args.directory / 'pixel-checks.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
