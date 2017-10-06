import bs4
from collections import OrderedDict
import copy
import numpy as np
import html
import warnings
from .extractor_wrapper import extractor_wrapper

warnings.filterwarnings("ignore", category=UserWarning, module='bs4')

tag_whitelist = [
    'sw-ex',
    'sl',
    'brev-y',
    'sw-ins',
    'sw-del',
    'sw-unclear',
    'sw-sup',
    'label',
    'graphic'
]


def clean_text(s):
    # remove unicode chars
    s_out = s.encode('ascii', 'ignore').decode('ascii')
    # remove span tags (these should never have been in the text to begin with)
    if '<' in s_out:
        soup = bs4.BeautifulSoup(s_out, 'html.parser')
        for match in soup.findAll():
            if (match.text.strip() == '') or (match.name not in tag_whitelist):
                match.unwrap()
        s_out = str(soup)
    # unescape html and repalce &nbsp; (\xa0) with a normal space
    s_out = html.unescape(s_out).replace('\xa0', ' ')
    return s_out


@extractor_wrapper
def sw_extractor(classification):
    blank_frame = OrderedDict([
        ('points', OrderedDict([('x', []), ('y', [])])),
        ('text', []),
        ('slope', [])
    ])
    extract = OrderedDict()
    frame = 'frame0'
    extract[frame] = copy.deepcopy(blank_frame)
    annotation = classification['annotations'][0]
    for value in annotation['value']:
        if ('startPoint' in value) and ('endPoint' in value) and ('text' in value):
            x = [value['startPoint']['x'], value['endPoint']['x']]
            y = [value['startPoint']['y'], value['endPoint']['y']]
            if (None not in x) and (None not in y):
                text = [clean_text(value['text'])]
                dx = x[-1] - x[0]
                dy = y[-1] - y[0]
                slope = np.rad2deg(np.arctan2(dy, dx))
                extract[frame]['text'].append(text)
                extract[frame]['points']['x'].append(x)
                extract[frame]['points']['y'].append(y)
                extract[frame]['slope'].append(slope)
    return extract