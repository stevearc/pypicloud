.. _upgrade0.4:

Uprading to 0.4.0
=================

This version was released to respond to pip 8.1.2 normalizing package names
differently. Read the discussion on :ref:`this pull request
<https://github.com/stevearc/pypicloud/pull/87>` for more information.

This will only affect packages with a ``_`` or ``.``, or multiple ``-``
characters in their name. If you don't have any, you may ignore these
instructions.

1) Rebuild your cache from storage, as per the instructions on :ref:`the upgrade
   page <upgrade>`

2) If you are using the file storage backend, you will need to rename any
   package name folder with those characters. You can ``cd`` into the package
   directory and run ``for name in *; do mv -T $name `echo $name | tr -s '_.-'
   '-'`; done``

Alternatively, if you have relatively few of these packages, you can just
re-upload them manually after the upgrade.
