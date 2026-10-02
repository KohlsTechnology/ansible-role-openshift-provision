"""
Produce short, human readable labels for OpenShift resources

Ansible prints the full loop item and registered result when tasks fail or
when they are skipped. Provisioning results embed the complete resource
definition, which can be several MB for resources. Using this filter in
``loop_control.label`` keeps that output small and prevents playbook logs 
from growing without bound
"""


def _is_resource(value):
    return isinstance(value, dict) and (
        'kind' in value or 'metadata' in value
    )


def _find_resource(value):
    """Return the resource dictionary embedded in a loop item or result."""
    if not isinstance(value, dict):
        return None

    # A plain resource definition
    if _is_resource(value):
        return value

    # A registered module result exposes the arguments it was invoked with
    invocation = value.get('invocation')
    if isinstance(invocation, dict):
        module_args = invocation.get('module_args')
        if isinstance(module_args, dict) and _is_resource(module_args.get('resource')):
            return module_args['resource']

    # Failure records and module results carry the resource directly
    if _is_resource(value.get('resource')):
        return value['resource']

    # A failure record wrapping another record or loop item
    item = value.get('item')
    if isinstance(item, dict):
        return _find_resource(item)

    return None


def resource_label(value, default='resource'):
    """
    Return a label in the form ``Kind namespace/name`` for the resource
    referenced by ``value``. ``value`` may be a resource definition, a
    registered module result, or a recorded failure
    """
    resource = _find_resource(value)
    if resource is None:
        return str(default)

    kind = resource.get('kind') or default
    metadata = resource.get('metadata')
    if not isinstance(metadata, dict):
        metadata = {}
    name = metadata.get('name')
    namespace = metadata.get('namespace')

    if namespace and name:
        return '%s %s/%s' % (kind, namespace, name)
    if name:
        return '%s %s' % (kind, name)
    return str(kind)


class FilterModule(object):
    '''Jinja2 filter for labeling OpenShift resources'''

    def filters(self):
        return {
            'resource_label': resource_label
        }
