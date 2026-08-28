"""Tests for sil permissions."""
import re
import types

from sil_auth_backends.utilities.utilities import PERM_NODE

import sil_advantage.permissions.perms.shortcuts
from sil_advantage.permissions import perms as server_perms
from sil_advantage.permissions import scopes as server_scopes


def validate_dups(lst):
    """Check if members of the list are unique."""
    if len(set(lst)) != len(lst):
        dups = [d for d in lst if lst.count(d) > 1]
        raise AssertionError("duplicates : {}".format(set(dups)))


def validate_name(item):
    """Validate name."""
    name = item[0]
    assert len(name) <= 100
    assert len(name) >= 3

    chars_regex = r"^[a-z0-9\._-]+$"
    assert re.match(chars_regex, name) is not None

    dot_underscore_regex = r"^[\._-]"
    assert re.match(dot_underscore_regex, name) is None

    slug_style_regex = r"^[a-z0-9]+[\._-]"
    assert re.match(slug_style_regex, name) is not None


def validate_parent_not_in_children(item):
    """Validate parent not in children."""
    if isinstance(item, PERM_NODE):
        all_children_name = []
        if item.children:
            for child in item.children:
                all_children_name.append(child[0])
            assert item.name not in all_children_name


def validate_description(item):
    """Validate description."""
    # Add project name len to the description
    name, desc = item[0], item[1]
    project_name = name.split(".")[0] + "."
    if len(name.split(".")) == 4:
        # add the ``global`` scope to be excluded
        project_name += name.split(".")[1] + "."
    # remove project_name and `separator` from the name
    # e.g ``sil_advantage.`` from ``sil_advantage.user_edit``
    assert len(desc) + len(project_name) >= len(name)
    assert desc[0] == desc[0].upper()


def validate_shortcuts(shorts, permlist, scopelist):
    """Validate shortcuts."""
    permscopes = permlist + scopelist
    extras = [
        "auth.is_branch_level",
        "auth.is_cluster_level",
        "auth.is_organisation_level",
        "auth.is_network_level",
        "auth.bp_view",
        "auth.user_view",
        "auth.user_create",
        "auth.user_edit",
        "auth.user_remove",
        "auth.permission_view",
        "auth.role_view",
        "auth.role_create",
        "auth.role_edit",
        "auth.role_delete",
        "auth.is_cross_network_level",
    ]
    permscopes += extras
    for hes in shorts:
        # check if shortcut is a list
        if isinstance(hes, list):
            # check if members of the list are unique
            validate_dups(hes)

            # check if members of the list are declared in
            # permissions.perms or permissions.scopes
            for pes in hes:
                assert pes in permscopes


def validate_perms(lst):
    """Validate permissions."""
    validate_dups([i[0] for i in lst])
    validate_dups([i[1] for i in lst])
    for x in lst:
        assert isinstance(x, tuple)
        validate_name(x)
        validate_description(x)
        validate_parent_not_in_children(x)


def get_module_members(module):
    """Retrieve the non 'private' members of the supplied module."""
    resolved_members = dir(module)
    return [
        getattr(module, r)
        for r in resolved_members
        if not r.startswith("_")
        and not isinstance(getattr(module, r), types.ModuleType)
    ]


def test_all():
    """Test combines all validators."""
    perms = get_module_members(server_perms)
    scopes = get_module_members(server_scopes)
    shorts = get_module_members(sil_advantage.permissions.perms.shortcuts)

    validate_perms(perms)
    validate_perms(scopes)
    validate_shortcuts(shorts, perms, scopes)
