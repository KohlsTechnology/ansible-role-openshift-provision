#!/usr/bin/env python3
"""Collect the API discovery snapshot used for kind availability deferral

Kubernetes exposes discovery in three levels:

  GET /api/v1            -> APIResourceList for the core group (has resources)
  GET /apis              -> APIGroupList (group + versions ONLY, no resources)
  GET /apis/<group>/<v>  -> APIResourceList for that group version (resources)

The grouped discovery document deliberately carries no resource list, so the
group versions have to be fetched individually before any kind can be called
"served". Skipping that step makes every grouped kind look unavailable, which
defers the whole cluster definition (MachineSets, ClusterAutoscaler) and
stalls the run on pods that can never schedule

"""

import json
import shlex
import subprocess
import sys

# Bounded per request so one slow or aggregated API group cannot stall the whole run
# failed versions are recorded and skipped
REQUEST_TIMEOUT = 20


def oc_raw(oc_cmd, url):
    """Fetch one discovery document, returning (doc, error_string)."""
    cmd = shlex.split(oc_cmd) + ['get', '--raw', url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=REQUEST_TIMEOUT)
    except Exception as exc:  # subprocess errors, timeouts
        return None, '%s: %s' % (type(exc).__name__, exc)
    if proc.returncode != 0:
        detail = (proc.stderr or '').strip().splitlines()
        return None, 'rc=%d %s' % (proc.returncode,
                                   detail[0] if detail else '')
    try:
        return json.loads(proc.stdout), None
    except ValueError as exc:
        return None, 'unparsable document: %s' % exc


def resource_kinds(doc):
    """Kind entries from an APIResourceList document"""
    kinds = []
    for res in (doc or {}).get('resources') or []:
        if not isinstance(res, dict):
            continue
        kind = res.get('kind')
        if kind:
            kinds.append(res)
    return kinds


def collect(oc_cmd):
    errors = []
    core_doc, err = oc_raw(oc_cmd, '/api/v1')
    if err:
        errors.append('/api/v1: ' + err)
    core_resources = resource_kinds(core_doc)

    group_list, err = oc_raw(oc_cmd, '/apis')
    if err:
        errors.append('/apis: ' + err)

    groups = []
    group_versions = 0
    skipped_versions = 0
    seen_versions = set()
    for group in (group_list or {}).get('groups') or []:
        if not isinstance(group, dict):
            continue
        versions = []
        for version in group.get('versions') or []:
            group_version = (version or {}).get('groupVersion')
            if not group_version or group_version in seen_versions:
                continue
            seen_versions.add(group_version)
            doc, verr = oc_raw(oc_cmd, '/apis/' + group_version)
            if verr:
                skipped_versions += 1
                errors.append('/apis/%s: %s' % (group_version, verr))
                continue
            resources = resource_kinds(doc)
            if not resources:
                skipped_versions += 1
                continue
            versions.append({'groupVersion': group_version,
                             'resources': resources})
            group_versions += 1
        if versions:
            groups.append({'name': group.get('name') or '', 'versions': versions})

    grouped_kinds = set()
    for group in groups:
        for version in group['versions']:
            api_group = version['groupVersion'].split('/')[0]
            for res in version['resources']:
                grouped_kinds.add('%s.%s' % (res['kind'], api_group))

    summary = {
        'core_resources': len(core_resources),
        'core_kinds': len({r.get('kind') for r in core_resources}),
        'group_versions': group_versions,
        'skipped_group_versions': skipped_versions,
        'group_kinds': len(grouped_kinds),
        'errors': errors[:10],
        'error_count': len(errors),
        'ok': bool(core_resources) and bool(grouped_kinds),
    }
    return {'resources': core_resources, 'groups': groups, 'summary': summary}


def main(argv):
    oc_cmd = argv[1] if len(argv) > 1 else 'oc'
    out_path = argv[2] if len(argv) > 2 else ''
    try:
        doc = collect(oc_cmd)
    except Exception as exc:
        doc = {
            'resources': [],
            'groups': [],
            'summary': {
                'ok': False,
                'core_kinds': 0,
                'group_kinds': 0,
                'errors': ['%s: %s' % (type(exc).__name__, exc)],
                'error_count': 1,
            },
        }
    payload = json.dumps(doc)
    if out_path:
        try:
            with open(out_path, 'w') as handle:
                handle.write(payload)
        except Exception as exc:
            print('WARNING: could not write %s: %s' % (out_path, exc),
                  file=sys.stderr)
    print(payload)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
