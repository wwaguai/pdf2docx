'''
Recognize content and format from PDF file with PyMuPDF
@created: 2019-06-24
@author: train8808@gmail.com
---

The raw page content extracted with with PyMuPDF, especially in JSON 
format is described per link:
https://pymupdf.readthedocs.io/en/latest/textpage/

The parsed results of this module is similar to the raw layout dict, 
but with some new features added, e.g.
 - add rectangle shapes (for text format, annotations)
 - add page margin
 - regroup lines in adjacent blocks considering context
 - recognize list format: block.type=2
 - recognize table format: block.type=3

An example of processed layout result:
    {
    "width" : 504.0,
    "height": 661.5,
    "margin": [20.4000, 574.9200, 37.5600, 806.4000], # left, right, top, bottom
    "blocks": [{...}, {...}, ...],
    "rects" : [{...}, {...}, ...]
    }

where:

`rects` are a list of rectangle shapes extracted from PDF xref_stream and
annotations:
    {
        'bbox' : [float,float,float,float], 
        'color': int,
        'type' : int or None
    }

`blocks` are a group of page contents. The type of blocks is extended from 
the default `text` and `image` to `list` and `table`:

- text block: type=0
- image block: type=1
- list block: type=2
- table block: type=3

Note: The length unit for each boundary box is pt, which is 1/72 Inch.

'''

import fitz
from .pdf_debug import debug_plot
from .pdf_table import parse_table
from .pdf_text import parse_text_and_image
from . import utils


def layout(layout, **kwargs):
    ''' processed page layout:
            - split block with multi-lines into seperated blocks
            - merge blocks vertically to complete sentence
            - merge blocks horizontally for convenience of docx generation

        args:
            layout: raw layout data extracted from PDF with `getText('rawdict')`,
                and with rectangles included.            

            kwargs: dict for layout plotting
                kwargs = {
                    'debug': bool,
                    'doc': fitz document or None,
                    'filename': str
                }            
    '''

    # preprocessing, e.g. change block order, clean negative block, 
    # get span text by joining chars
    preprocessing(layout)
    
    # parse table blocks: 
    #  - table structure/format recognized from rectangles
    #  - cell contents extracted from text blocks
    parse_table(layout, **kwargs)

    # parse text and image blocks:
    #  - check inline images
    #  - parse text format, e.g. highlight, underline
    parse_text_and_image(layout, **kwargs)
    
    # paragraph / line spacing
    parse_vertical_spacing(layout)


def preprocessing(layout):
    '''preprocessing for the raw layout of PDF page'''
    # remove blocks exceeds page region: negative bbox
    layout['blocks'] = list(filter(
        lambda block: all(x>0 for x in block['bbox']), 
        layout['blocks']))

    # reorder to reading direction:
    # from up to down, from left to right
    layout['blocks'].sort(
        key=lambda block: (block['bbox'][1], 
            block['bbox'][0]))

    # joining chars in span
    for block in layout['blocks']:
        # skip image
        if block['type']==1: continue

        # join chars
        for line in block['lines']:
            for span in line['spans']:
                chars = [char['c'] for char in span['chars']]
                span['text'] = ''.join(chars)

    # round bbox of rectangles: one decimal place is enough, 
    # otherwise, would encounter float error, especially get intersection of two bbox-es
    for rect in layout['rects']:
        rect['bbox'] = tuple([round(x,1) for x in rect['bbox']])

    # anything changed in this step?
    return True


def parse_vertical_spacing(layout):
    ''' Calculate external and internal vertical space for paragraph blocks under page context 
        or table context. It'll used as paragraph spacing and line spacing when creating paragraph.
    '''
    # blocks in page level
    top, bottom = layout['margin'][-2:]
    _parse_paragraph_and_line_spacing(layout['blocks'], top, layout['height']-bottom)

    # blocks in table cell level
    tables = list(filter(lambda block: block['type']==3, layout['blocks']))
    for table in tables:
        for row in table['cells']:
            for cell in row:
                if not cell: continue
                _, y0, _, y1 = cell['bbox']
                w_top, _, w_bottom, _ = cell['border-width']
                _parse_paragraph_and_line_spacing(cell['blocks'], y0+w_top/2.0, y1-w_bottom/2.0)


def page_margin(layout):
    '''get page margin:
       - left: as small as possible in x direction and should not intersect with any other bbox
       - right: MIN(left, width-max(bbox[3]))
       - top: MIN(bbox[1])
       - bottom: height-MAX(bbox[3])
    '''

    # check candidates for left margin:
    list_bbox = list(map(lambda x: x['bbox'], layout['blocks']))
    list_bbox.sort(key=lambda x: (x[0], x[2]))
    lm_bbox, num = list_bbox[0], 0
    candidates = []
    for bbox in list_bbox:
        # count of blocks with save left border
        if abs(bbox[0]-lm_bbox[0])<utils.DM:
            num += 1
        else:
            # stop counting if current block border is not equal to previous,
            # then get the maximum count of aligned blocks
            candidates.append((lm_bbox, num))

            # start to count current block border. this border is invalid if intersection with 
            # previous block occurs, so count it as -1
            num = 1 if bbox[0]>lm_bbox[2] else -1

        lm_bbox = bbox
    else:
        candidates.append((lm_bbox, num)) # add last group

    # if nothing found, e.g. whole page is an image, return standard margin
    if not candidates:
        return (utils.ITP, ) * 4 # 1 Inch = 72 pt

    # get left margin which is supported by bbox-es as more as possible
    candidates.sort(key=lambda x: x[1], reverse=True)
    left = candidates[0][0][0]

    # right margin
    x_max = max(map(lambda x: x[2], list_bbox))
    w, h = layout['width'], layout['height']
    right = min(w-x_max, left)

    # top/bottom margin
    top = min(map(lambda x: x[1], list_bbox))
    bottom = h-max(map(lambda x: x[3], list_bbox))

    return left, right, min(utils.ITP, top), min(utils.ITP, bottom)


def _parse_paragraph_and_line_spacing(blocks, Y0, Y1):
    ''' Calculate external and internal vertical space for text blocks.
     
        - paragraph spacing is determined by the vertical distance to previous block. 
          For the first block, the reference position is top margin.
        
            It's easy to set before-space or after-space for a paragraph with python-docx,
            so, if current block is a paragraph, set before-space for it; if current block 
            is not a paragraph, e.g. a table, set after-space for previous block (generally, 
            previous block should be a paragraph).
        
        - line spacing is defined as the average line height in current block.

        ---
        Args:
            - blocks: a list of block within a page/table cell
            - X0, X1: the blocks are restricted in a vertical range within (Y0, Y1)
    '''
    ref_block = None
    ref_pos = Y0
    for block in blocks:

        # NOTE: the table bbox is counted on center-line of outer borders, so a half of top border
        # size should be excluded from the calculated vertical spacing
        if block['type']==3:
            dw = block['cells'][0][0]['border-width'][0] / 2.0 # use top border of the first cell
        else:
            dw = 0.0

        start_pos = block['bbox'][1] - dw
        para_space = start_pos - ref_pos

        # paragraph-1 (ref) to paragraph-2 (current): set before-space for paragraph-2
        if block['type']==0:

            # spacing before this paragraph
            block['before_space'] = para_space

            # calculate average line spacing in paragraph
            # e.g. line-space-line-space-line, excepting first line -> space-line-space-line,
            # so an average line height = space+line
            # then, the height of first line can be adjusted by updating paragraph before-spacing.
            # 
            ref_bbox = None
            count = 0
            for line in block['lines']:
                # count of lines
                if not utils.is_horizontal_aligned(line['bbox'], ref_bbox, True, 0.5):
                    count += 1
                # update reference line
                ref_bbox = line['bbox']
            
            _, y0, _, y1 = block['lines'][0]['bbox']   # first line
            first_line_height = y1 - y0
            block_height = block['bbox'][3]-block['bbox'][1]
            if count > 1:
                line_space = (block_height-first_line_height)/(count-1)
            else:
                line_space = block_height
            block['line_space'] = line_space

            # if only one line exists, don't have to set line spacing, use default setting,
            # i.e. single line instead
            if count > 1:
                # since the line height setting in docx may affect the original bbox in pdf, 
                # it's necessary to update the before spacing:
                # taking bottom left corner of first line as the reference point                
                para_space = para_space + first_line_height - line_space
                block['before_space'] = para_space

            # adjust last block to avoid exceeding current page
            free_space = Y1-(ref_pos+para_space+block_height) 
            if free_space<=0:
                block['before_space'] = para_space+free_space-utils.DM

        # paragraph (ref) to table (current): set after-space for paragraph        
        elif ref_block['type']==0:
            ref_block['after_space'] = para_space

        # situation with very low probability, e.g. table to table
        else:
            pass

        # update reference block        
        ref_block = block
        ref_pos = block['bbox'][3] + dw
