# How to contribute
(Based on the [ATOM Contributor Guidelines](https://github.com/atom/atom/blob/master/CONTRIBUTING.md))

Many thanks for considering contributing to OpenVDM.

#### Table Of Contents

[Code of Conduct](#code-of-conduct)

[I don't want to read this whole thing, I just have a question!!!](#i-dont-want-to-read-this-whole-thing-i-just-have-a-question)

[What should I know before I get started?](#what-should-i-know-before-i-get-started)

[How Can I Contribute?](#how-can-i-contribute)
  * [Reporting Bugs](#reporting-bugs)
  * [Suggesting Enhancements](#suggesting-enhancements)
  * [Your First Code Contribution](#your-first-code-contribution)
  * [Git Commits and Pull Requests](#git-commits-and-pull-requests)

[Styleguides](#styleguides)
  * [Python Styleguide](#python-styleguide)
  * [JavaScript Styleguide](#javascript-styleguide)
  * [Documentation Styleguide](#documentation-styleguide)

## Code of Conduct

This project and everyone participating in it is governed by the [OpenVDM Code of Conduct](CODE_OF_CONDUCT.md). By 
participating, you are expected to uphold this code. Please report unacceptable behavior to 
[oceandatatools@github.com](mailto:oceandatatools@github.com).

## I don't want to read this whole thing I just have a question!!!

> **Note:** Please don't file an issue to ask a question. You'll get faster results by using the resources below.

* If you haven't already, please join the [OpenVDM mailing list](https://groups.google.com/forum/#!forum/openrvdm).
* If chat is more your speed, please join the [OpenVDM Slack channel](https://oceandatarat.slack.com) to ask your questions there.
    * Even though Slack is a chat service, sometimes it takes several hours for community members to respond &mdash; please be patient!
    * Use the `#general` channel for general questions or discussion about OpenVDM
    * Use the `#openvdm` channel for technical questions about OpenVDM

## What should I know before I get started?

OpenVDM is largely a volunteer effort. Most folks involved in the project have demanding day jobs and are supporting the
code in their spare time. They may not be able to respond quickly and comprehensively to every question.

The OpenVDM architecture is intended to be modular, extensible and as platform-independent as practical. Contributors should
consider how their proposed changes will affect the 

## How Can I Contribute?

### Reporting Bugs

This section guides you through submitting a bug report for OpenVDM. Following these guidelines helps maintainers and
the community understand your report, reproduce the behavior, and find related reports.

Before creating bug reports, please check [this list](#before-submitting-a-bug-report) as you might find out that you
don't need to create one. When you are creating a bug report, please
[include as many details as possible](#how-do-i-submit-a-good-bug-report). Fill out 
the required template, the information it asks for helps us resolve issues faster.

> **Note:** If you find a **Closed** issue that seems like it is the same thing that you're experiencing, open a new
issue and include a link to the original issue in the body of your new one.

#### Before Submitting A Bug Report

* **Perform a [cursory search](https://github.com/oceandatatools/openvdm/issues)** to see if the problem has already been
  reported. If it has **and the issue is still open**, add a comment to the existing issue instead of opening a new one.

#### How Do I Submit A (Good) Bug Report?

Bugs are tracked as [GitHub issues](https://guides.github.com/features/issues/).
Explain the problem and include additional details to help maintainers reproduce the problem:

* **Use a clear and descriptive title** for the issue to identify the problem.
* **Describe the exact steps which reproduce the problem** in as many details as possible.
* **Provide specific examples to demonstrate the steps**. Include links to files or GitHub projects, or copy/pasteable snippets, which you use in those examples. If you're providing snippets in the issue, use [Markdown code blocks](https://help.github.com/articles/markdown-basics/#multiple-lines).
* **Describe the behavior you observed after following the steps** and point out what exactly is the problem with that behavior.
* **Explain which behavior you expected to see instead and why.**
* **If the problem is related to performance or memory**, include a CPU profile capture if able.
* **If the problem wasn't triggered by a specific action**, describe what you were doing before the problem happened and share more information using the guidelines below.

Provide more context by answering these questions:

* **Did the problem start happening recently** (e.g. after updating to a new version) or was this always a problem?
* **Can you reliably reproduce the issue?** If not, provide details about how often the problem happens and under which conditions it normally happens.

Include details about your configuration and environment:

* **Which version of the code are you using?** 
* **What's the name and version of the OS you're using**?
* **Are you running OpenVDM in a virtual machine?** If so, which VM software are you using and which operating systems and versions are used for the host and the guest?

### Suggesting Enhancements

This section guides you through submitting an enhancement suggestion for OpenVDM, including completely new features and minor improvements to existing functionality. Following these guidelines helps maintainers and the community understand your suggestion and find related suggestions.

Before creating enhancement suggestions, please check [this list](#before-submitting-an-enhancement-suggestion) as you might find out that you don't need to create one. When you are creating an enhancement suggestion, please [include as many details as possible](#how-do-i-submit-a-good-enhancement-suggestion). Fill in [the template](https://github.com/atom/.github/blob/master/.github/ISSUE_TEMPLATE/feature_request.md), including the steps that you imagine you would take if the feature you're requesting existed.

#### Before Submitting An Enhancement Suggestion

* **Perform a [cursory search](https://github.com/oceandatatools/openvdm/issues)** to see if the enhancement has already been suggested. If it has, add a comment to the existing issue instead of opening a new one.

#### How Do I Submit A (Good) Enhancement Suggestion?

Enhancement suggestions are tracked as [GitHub issues](https://guides.github.com/features/issues/). After you've determined [which repository](#atom-and-packages) your enhancement suggestion is related to, create an issue on that repository and provide the following information:

* **Use a clear and descriptive title** for the issue to identify the suggestion.
* **Provide a step-by-step description of the suggested enhancement** in as many details as possible.
* **Provide specific examples to demonstrate the steps**. Include copy/pasteable snippets which you use in those examples, as [Markdown code blocks](https://help.github.com/articles/markdown-basics/#multiple-lines).
* **Describe the current behavior** and **explain which behavior you expected to see instead** and why.
* **Explain why this enhancement would be useful** to OpenVDM users.

### Your First Code Contribution

Unsure where to begin contributing to OpenVDM? You can start by looking through these `good first issue` and `help-wanted` issues:

* [Good first issue](good-first-issue) - issues which should only require a few lines of code, and a test or two.
* [Help wanted issues](help-wanted) - issues which should be a bit more involved than `beginner` issues.

Both issue lists are sorted by total number of comments. While not perfect, number of comments is a reasonable proxy for impact a given change will have.

Once you have selected an issue to work on, say 'issue 57', create a fork of the repository into your own GitHub account. Check out the ``dev`` branch and create from it a new branch with the name of the issue you've selected:

```
git branch issue_57
git checkout issue_57
```

When your contribution is ready, submit a pull request, requesting that it be merged back into the OpenVDM ``dev`` branch. The ``dev`` branch will be merged into the ``master`` branch when new numbered versions are released.

### Git Commits and Pull Requests

Prior to submitting any pull request, please run the checks below and make sure they pass. Install the pre-commit hooks once so they also run on every commit:

```
cd <openvdm_root>
source ./venv/bin/activate
pre-commit install
cd www && composer install && cd ..     # installs PHPStan (a dev dependency)
```

Then, before opening a pull request:

```
source ./venv/bin/activate
python -m pytest server        # see CLAUDE.md for the three expected false-positive errors
pre-commit run --all-files     # ruff, ESLint, php -l and PHPStan
```

The PHP checks use your locally installed PHP (8.3 matches production) and are skipped with a message if PHP or PHPStan isn't installed.

There is no automated test suite for the PHP or JavaScript, so changes to the web UI also need a manual check in a browser. New Python functionality should, if at all possible, be accompanied by a new unit test.

Always write a clear log message for your commits. One-line messages are fine for small changes, but bigger changes
should look like this:

    $ git commit -m "A brief summary of the commit
    > 
    > A paragraph describing what changed and its impact."
    
Please send a [GitHub Pull Request to oceandatatools/openvdm/dev](https://github.com/oceandatatools/openvdm/pull/new/dev) with
a clear list of what you've done (read more about [pull requests](http://help.github.com/pull-requests/)). When you send
a pull request, we will love you forever if you include examples. We can always use more test coverage. Please follow
our coding conventions (below) and make sure all of your commits are atomic (one feature per commit).

## Styleguides

### Python Styleguide

* With few exceptions, we try to adhere to PEP8 and the [Google Python Style Guide](http://google.github.io/styleguide/pyguide.html)
* The primary exceptions are
   * We (grudgingly) allow a maximum line length of 100 characters
   * All unqualified imports (``import foo``) are clustered alphabetically before qualified imports (``from foo import bar``).
* We test code compliance with PEP8 with `pylint`
  * Install pylint with `pip install pylint`
  * Run from project root with `pylint [subdir path]`
  * Add pragma comments to disable warnings on a line-by-line basis, e.g.
  
      ```from foo import bar  # noqa: E401, F502```
* Do not mix styles: when editing a pre-existing file, strive for consistency with the file's style over adherence with the Style Guide.
 
### JavaScript Styleguide

Match the style of the existing code: 4-space indentation, semicolons, `var`, and page scripts wrapped in jQuery `$(function () { ... })`.

* ESLint (`eslint.config.mjs`) checks for bugs only (undefined names, unused and duplicate variables, unreachable code), not formatting. It runs from pre-commit.
* Variables defined outside the file being linted (libraries, the inline `<script>` in `www/app/templates/default/footer.php`, helpers such as `mapBaseLayers.js`) must be listed in the config's globals. A script that defines a helper for other files marks it with `/* exported name */`.

### PHP Styleguide

Follow the existing MVC conventions in `www/app/`.

* PHPStan (`www/phpstan.neon`, level 1) runs from pre-commit. Findings that existed when it was added are recorded in `www/phpstan-baseline.neon`. New code must not add to it. When you fix a baselined finding, regenerate the baseline from `www/`: `vendor/bin/phpstan analyse --generate-baseline phpstan-baseline.neon`
* Give class properties a type (e.g. `private \Models\Warehouse $_warehouseModel;`) when you add or touch them. Untyped properties are `mixed` to PHPStan, so calls to methods that don't exist on them aren't caught.
* Declare every property the class uses. Dynamic properties are deprecated as of PHP 8.2.

### Documentation Styleguide

* Use [Markdown](https://daringfireball.net/projects/markdown).
* Reference methods and classes in markdown with the custom `{}` notation:
    * Reference classes with `{ClassName}`
    * Reference instance methods with `{ClassName::methodName}`
    * Reference class methods with `{ClassName.methodName}`
