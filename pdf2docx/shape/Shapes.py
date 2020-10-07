# -*- coding: utf-8 -*-

'''
A group of Shape instances.

@created: 2020-09-15
@author: train8808@gmail.com
'''

from .Shape import Shape, Stroke, Fill
from ..common.base import RectType, lazyproperty
from ..common.Collection import Collection
from ..common import utils
from ..common import constants


class Shapes(Collection):

    def from_dicts(self, raws:list):
        '''Initialize Stroke/Fill from dicts.'''
        # distinguish Stroke and Fill: whether keys 'start' and 'end' exist in dict
        for raw in raws:
            shape = Stroke(raw) if 'start' in raw else Fill(raw)
            # add to list
            self.append(shape)
        
        return self


    def _update_bbox(self, shape:Shape):
        ''' override. Do nothing.'''
        pass


    @property
    def borders(self):
        '''Shapes in border type.'''
        instances = list(filter(
            lambda shape: shape.type==RectType.BORDER, self._instances))
        return Shapes(instances)


    @lazyproperty
    def strokes(self):
        '''Stroke Shapes. Lazy property, cache it once calculated since it doesn't change generally.'''
        instances = list(filter(
            lambda shape: isinstance(shape, Stroke), self._instances))
        return Shapes(instances)


    @lazyproperty
    def fillings(self):
        '''Fill Shapes. Lazy property, cache it once calculated since it doesn't change generally.'''
        instances = list(filter(
            lambda shape: isinstance(shape, Fill), self._instances))
        return Shapes(instances)


    def clean(self):
        '''Clean rectangles:
            - delete rectangles fully contained in another one (beside, they have same bg-color)
            - join intersected and horizontally aligned rectangles with same height and bg-color
            - join intersected and vertically aligned rectangles with same width and bg-color
        '''
        # sort in reading order
        self.sort_in_reading_order()

        # remove shapes out of page
        page_bbox = (0.0, 0.0, self.parent.width, self.parent.height)
        f = lambda shape: shape.bbox.intersects(page_bbox)
        shapes = filter(f, self._instances)

        # merge shapes if:
        # - same filling color, and
        # - intersected in same raw/col, or overlapped significantly
        shapes_unique = [] # type: list [Shape]
        for shape in shapes:
            for ref_shape in shapes_unique:
                # Do nothing if these two shapes in different bg-color
                if ref_shape.color!=shape.color: continue     

                # combine two shapes in a same row if any intersection exists
                # ideally the aligning threshold should be 1.0, tolerance is considered here
                if shape.horizontally_align_with(ref_shape, constants.FACTOR_SAME): 
                    main_bbox = utils.get_main_bbox(shape.bbox, ref_shape.bbox, 0.0)

                # combine two shapes in a same column if any intersection exists
                elif shape.vertically_align_with(ref_shape, constants.FACTOR_SAME):
                    main_bbox = utils.get_main_bbox(shape.bbox, ref_shape.bbox, 0.0)

                # combine two shapes if they have a large intersection
                else:
                    main_bbox = utils.get_main_bbox(shape.bbox, ref_shape.bbox, constants.FACTOR_A_HALF)

                if main_bbox:
                    ref_shape.update_bbox(main_bbox)
                    break            
            else:
                shapes_unique.append(shape)
                
        # convert Fill instance to Stroke if looks like stroke
        shapes = []
        for shape in shapes_unique:
            if isinstance(shape, Stroke):
                shapes.append(shape)
            else:
                stroke = shape.to_stroke()
                shapes.append(stroke if stroke else shape)

        self.reset(shapes)

        return True


    def contained_in_bbox(self, bbox):
        ''' Filter shapes contained in target bbox.
            ---
            Args:
            - bbox: fitz.Rect
        '''
        instances = list(filter(
            lambda shape: shape.bbox & bbox, self._instances))
        return Shapes(instances)


    def containing_bbox(self, bbox, threshold:float):
        ''' Get the shape containing target bbox.
            ---
            Args:
            - bbox: fitz.Rect, target bbox
            - threshold: regard as contained if the intersection exceeds this threshold
        '''
        s = bbox.getArea()
        if not s: return None

        for instance in self._instances:
            intersection = bbox & instance.bbox
            if intersection.getArea() / s >= threshold: return instance

        return None