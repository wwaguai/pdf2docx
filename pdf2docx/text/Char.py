# -*- coding: utf-8 -*-

'''
Char object based on PDF raw dict extracted with PyMuPDF.

@created: 2020-07-22

---

refer to: https://pymupdf.readthedocs.io/en/latest/textpage.html

raw dict for Char
    {
        'bbox'  : (x0, y0, x1, y1), 
        'c'     : str, 
        'origin': (x,y)
    }
'''


from ..common.Element import Element
from ..shape.Shape import Shape


class Char(Element):
    '''Object representing a character.'''
    def __init__(self, raw:dict=None):
        if raw is None: raw = {}
        self.c = raw.get('c', '')
        self.origin = raw.get('origin', None)
        super().__init__(raw) # NOTE: ignore parent element for Char instance


    def contained_in_rect(self, rect:Shape, horizontal:bool=True):
        ''' Detect whether locates in a rect, or has an intersection 
            larger than half of the char bbox.
        '''
        # char in rect?
        if self.bbox in rect.bbox:
            return True

        # intersection?
        else:
            intsec = self.bbox & rect.bbox
            if horizontal:
                return intsec.width > 0.5*self.bbox.width
            else:
                return intsec.height > 0.5*self.bbox.height


    def store(self):
        res = super().store()
        res.update({
            'c': self.c,
            'origin': self.origin
        })

        return res