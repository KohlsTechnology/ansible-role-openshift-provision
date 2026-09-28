"""
Normalize a failed openshift_provision result into a compact record

Failure records keep only what the role needs to retry a resource
(``failed``, the resource definition, the module arguments and the error
message). Previously this was assembled with a ``set_fact`` loop, which
caused Ansible to print the growing failure list once per loop item.
Building the records with a single expression keeps output and memory
proportional to the number of failures
"""


def _module_args(result):
    invocation = result.get('invocation')
    if isinstance(invocation, dict):
        module_args = invocation.get('module_args')
        if isinstance(module_args, dict):
            return module_args
    return {}


def _resource(result, module_args):
    if isinstance(module_args.get('resource'), dict):
        return module_args['resource']
    if isinstance(result.get('resource'), dict):
        return result['resource']
    if isinstance(result.get('item'), dict):
        return result['item']
    return {}


def record_failure(result):
    """Return a retryable failure record for a failed module result"""
    if not isinstance(result, dict):
        result = {}
    module_args = _module_args(result)
    return {
        'failed': True,
        'resource': _resource(result, module_args),
        'invocation': {'module_args': module_args},
        'msg': result.get('msg', ''),
    }


class FilterModule(object):
    '''Jinja2 filter for building retryable failure records'''

    def filters(self):
        return {
            'record_failure': record_failure
        }
