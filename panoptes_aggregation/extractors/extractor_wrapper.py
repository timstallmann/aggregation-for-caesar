import ast
from functools import wraps
from ..append_version import append_version
from .utilities import pluck_fields


def unpack_annotations(annotations, task):
    annotations_list = []
    for key, value in annotations.items():
        # subtasks are stored as 'T0.0.0' and need to be pulled out with 'T0'
        if (task == 'all') or (key.split('.')[0] == task):
            annotations_list += value
    return annotations_list


def extractor_wrapper(gold_standard=False):
    def decorator(func):
        @wraps(func)
        def wrapper(argument, **kwargs):
            #: check if argument is a flask request
            if hasattr(argument, 'get_json'):
                kwargs = argument.args.copy().to_dict()
                if 'details' in kwargs:
                    kwargs['details'] = ast.literal_eval(kwargs['details'])
                if 'tools' in kwargs:
                    kwargs['tools'] = ast.literal_eval(kwargs['tools'])
                data = argument.get_json()
            else:
                data = argument
            task = kwargs.pop('task', 'all')
            no_version = kwargs.pop('no_version', False)
            annotations = data['annotations']
            annotations_list = unpack_annotations(annotations, task)
            data['annotations'] = annotations_list
            if gold_standard:
                kwargs['gold_standard'] = data.get('gold_standard', False)
            extraction = func(data, **kwargs)
            # add package version to the extracted content
            if not no_version:
                append_version(extraction)

            ## RS 2021/09/14
            ## if the pluck parameter exists
            ## append the required data from the pluckfield extractor
            ## to the output data
            pluck = kwargs.get('pluck', None)
            if pluck is not None:
                ## get the data and corresponding keys
                pluck_values = pluck_fields(data, pluck)

                ## append the data with its corresponding
                ## key to the output data
                for key in pluck_values.keys():
                    extraction[key] = pluck_values[key]

            return extraction
        wrapper._original = func
        return wrapper
    return decorator
