"""What an install calls cruises and lowerings, for the workers' messages.

The installer can name them something else, e.g. Voyage and Dive
(``CRUISE_NAME``, ``LOWERING_NAME`` and their plurals in ``Config.php``,
#684). The web app uses those names, and so do the READMEs and the
workers' OpenVDM messages, task part names and failure reasons (#685). A
worker gets them once per job with :func:`fetch_terms`, and words its
messages with the :class:`Terms` attributes, e.g.
``f"Verify {terms.cruise_lower} directory exists"``. Log messages keep
saying cruise and lowering.
"""

import logging
import re

from server.lib.openvdm import DEFAULT_TERMS


def lower_term(name: str) -> str:
    """Return a cruise or lowering name as it reads in a sentence (#684).

    Each word in lower case, except one in capitals, such as an acronym, as
    ``Helpers\\Terms::lower()`` does in the web app: "ROV Dive" gives
    "ROV dive".

    Args:
        name: The name, e.g. ``'Voyage'``.

    Returns:
        str: e.g. ``'voyage'``.
    """
    return re.sub(r'[^\s-]+', lambda m: m.group(0) if len(m.group(0)) > 1 and m.group(0).isupper()
                  else m.group(0).lower(), name)


class Terms:  # pylint: disable=too-few-public-methods
    """The names an install uses for cruises and lowerings.

    Attributes:
        cruise: e.g. ``'Voyage'``, as the install spells it, for the start of
            a sentence or a title.
        cruises: The plural, e.g. ``'Voyages'``.
        lowering: e.g. ``'ROV Dive'``.
        lowerings: e.g. ``'ROV Dives'``.
        cruise_lower: For the middle of a sentence (:func:`lower_term`),
            e.g. ``'voyage'``; also ``cruises_lower``, ``lowering_lower``
            (``'ROV dive'``) and ``lowerings_lower``.
    """

    def __init__(self, names=None) -> None:
        """Take the names from ``OpenVDM.get_terms()``.

        Args:
            names: ``cruise``, ``cruises``, ``lowering`` and ``lowerings``;
                :data:`server.lib.openvdm.DEFAULT_TERMS`' value for any
                missing or empty, and all of them if *names* isn't a dict.
        """
        names = names if isinstance(names, dict) else {}
        for key, default in DEFAULT_TERMS.items():
            value = str(names.get(key) or default)
            setattr(self, key, value)
            setattr(self, f'{key}_lower', lower_term(value))

    def as_dict(self) -> dict:
        """Return the names and their ``_lower`` forms, e.g. for a template.

        Returns:
            dict: ``{'cruise': ..., 'cruise_lower': ..., ...}``.
        """
        return dict(vars(self))


def fetch_terms(ovdm) -> Terms:
    """Return the install's names from the OpenVDM API, or the defaults.

    A message is better worded with the default names than not sent, so an
    API error is logged and the defaults are used.

    Args:
        ovdm: The ``OpenVDM`` API wrapper.

    Returns:
        Terms: The install's names.
    """
    try:
        return Terms(ovdm.get_terms())
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.warning("Using the default names for cruises and lowerings: %s", exc)
        return Terms()
