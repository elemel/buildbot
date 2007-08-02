
from twisted.web import html
from twisted.web.util import Redirect, DeferredResource
from twisted.internet import defer, reactor

import urllib
from twisted.python import log
from buildbot.status.web.base import HtmlResource, make_row

from buildbot.status.web.tests import TestsResource
from buildbot.status.web.step import StepsResource

# builders/$builder/builds/$buildnum
class StatusResourceBuild(HtmlResource):
    title = "Build"
    addSlash = True

    def __init__(self, build_status, build_control, builder_control):
        HtmlResource.__init__(self)
        self.build_status = build_status
        self.build_control = build_control
        self.builder_control = builder_control

    def body(self, req):
        b = self.build_status
        status = self.getStatus(req)
        buildbotURL = status.getBuildbotURL()
        projectName = status.getProjectName()
        data = '<div class="title"><a href="%s">%s</a></div>\n'%(buildbotURL,
                                                                 projectName)
        # the color in the following line gives python-mode trouble
        builder_name = b.getBuilder().getName()
        data += ("<h1><a href=\"../../%s\">Builder %s</a>: Build #%d</h1>\n"
                 % (urllib.quote(builder_name), builder_name, b.getNumber()))
        data += "<h2>Buildslave:</h2>\n %s\n" % html.escape(b.getSlavename())
        data += "<h2>Reason:</h2>\n%s\n" % html.escape(b.getReason())

        ss = b.getSourceStamp()
        data += "<h2>SourceStamp:</h2>\n"
        data += " <ul>\n"
        if ss.branch:
            data += "  <li>Branch: %s</li>\n" % html.escape(ss.branch)
        if ss.revision:
            data += "  <li>Revision: %s</li>\n" % html.escape(str(ss.revision))
        if ss.patch:
            data += "  <li>Patch: YES</li>\n" # TODO: provide link to .diff
        if ss.changes:
            data += "  <li>Changes: see below</li>\n"
        if (ss.branch is None and ss.revision is None and ss.patch is None
            and not ss.changes):
            data += "  <li>build of most recent revision</li>\n"
        data += " </ul>\n"
        if b.isFinished():
            data += "<h2>Results:</h2>\n"
            data += " ".join(b.getText()) + "\n"
            if b.getTestResults():
                url = req.childLink("tests")
                data += "<h3><a href=\"%s\">test results</a></h3>\n" % url
        else:
            data += "<h2>Build In Progress</h2>"
            if self.build_control is not None:
                stopURL = urllib.quote(req.childLink("stop"))
                data += """
                <form action="%s" class='command stopbuild'>
                <p>To stop this build, fill out the following fields and
                push the 'Stop' button</p>\n""" % stopURL
                data += make_row("Your name:",
                                 "<input type='text' name='username' />")
                data += make_row("Reason for stopping build:",
                                 "<input type='text' name='comments' />")
                data += """<input type="submit" value="Stop Builder" />
                </form>
                """

        if b.isFinished() and self.builder_control is not None:
            data += "<h3>Resubmit Build:</h3>\n"
            # can we rebuild it exactly?
            exactly = (ss.revision is not None) or b.getChanges()
            if exactly:
                data += ("<p>This tree was built from a specific set of \n"
                         "source files, and can be rebuilt exactly</p>\n")
            else:
                data += ("<p>This tree was built from the most recent "
                         "revision")
                if ss.branch:
                    data += " (along some branch)"
                data += (" and thus it might not be possible to rebuild it \n"
                         "exactly. Any changes that have been committed \n"
                         "after this build was started <b>will</b> be \n"
                         "included in a rebuild.</p>\n")
            rebuildURL = urllib.quote(req.childLink("rebuild"))
            data += ('<form action="%s" class="command rebuild">\n'
                     % rebuildURL)
            data += make_row("Your name:",
                             "<input type='text' name='username' />")
            data += make_row("Reason for re-running build:",
                             "<input type='text' name='comments' />")
            data += '<input type="submit" value="Rebuild" />\n'
            data += '</form>\n'

        data += "<h2>Steps and Logfiles:</h2>\n"
        if b.getLogs():
            data += "<ol>\n"
            for s in b.getSteps():
                name = s.getName()
                data += (" <li><a href=\"%s\">%s</a> [%s]\n"
                         % (req.childLink("steps/%s" % urllib.quote(name)),
                            name,
                            " ".join(s.getText())))
                if s.getLogs():
                    data += "  <ol>\n"
                    for logfile in s.getLogs():
                        logname = logfile.getName()
                        logurl = req.childLink("steps/%s/logs/%s" %
                                               (urllib.quote(name),
                                                urllib.quote(logname)))
                        data += ("   <li><a href=\"%s\">%s</a></li>\n" %
                                 (logurl, logfile.getName()))
                    data += "  </ol>\n"
                data += " </li>\n"
            data += "</ol>\n"

        data += ("<h2>Blamelist:</h2>\n"
                 " <ol>\n")
        for who in b.getResponsibleUsers():
            data += "  <li>%s</li>\n" % html.escape(who)
        data += (" </ol>\n"
                 "<h2>All Changes</h2>\n")
        changes = ss.changes
        if changes:
            data += "<ol>\n"
            for c in changes:
                data += "<li>" + c.asHTML() + "</li>\n"
            data += "</ol>\n"
        #data += html.PRE(b.changesText()) # TODO
        return data

    def stop(self, req):
        b = self.build_status
        c = self.build_control
        log.msg("web stopBuild of build %s:%s" % \
                (b.getBuilder().getName(), b.getNumber()))
        name = req.args.get("username", ["<unknown>"])[0]
        comments = req.args.get("comments", ["<no reason specified>"])[0]
        reason = ("The web-page 'stop build' button was pressed by "
                  "'%s': %s\n" % (name, comments))
        c.stopBuild(reason)
        # we're at http://localhost:8080/svn-hello/builds/5/stop?[args] and
        # we want to go to: http://localhost:8080/svn-hello/builds/5 or
        # http://localhost:8080/
        #
        #return Redirect("../%d" % self.build.getNumber())
        r = Redirect("../../..") # TODO: no longer correct
        d = defer.Deferred()
        reactor.callLater(1, d.callback, r)
        return DeferredResource(d)

    def rebuild(self, req):
        b = self.build_status
        bc = self.builder_control
        log.msg("web rebuild of build %s:%s" % \
                (b.getBuilder().getName(), b.getNumber()))
        name = req.args.get("username", ["<unknown>"])[0]
        comments = req.args.get("comments", ["<no reason specified>"])[0]
        reason = ("The web-page 'rebuild' button was pressed by "
                  "'%s': %s\n" % (name, comments))
        if not bc or not b.isFinished():
            log.msg("could not rebuild: bc=%s, isFinished=%s"
                    % (bc, b.isFinished()))
            # TODO: indicate an error
        else:
            bc.resubmitBuild(b, reason)
        # we're at http://localhost:8080/svn-hello/builds/5/rebuild?[args] and
        # we want to go to the top, at http://localhost:8080/
        r = Redirect("../../..") # TODO: no longer correct
        d = defer.Deferred()
        reactor.callLater(1, d.callback, r)
        return DeferredResource(d)

    def getChild(self, path, req):
        if path == "stop":
            return self.stop(req)
        if path == "rebuild":
            return self.rebuild(req)
        if path == "steps":
            return StepsResource(self.build_status)
        if path == "tests":
            return TestsResource(self.build_status)

        return HtmlResource.getChild(self, path, req)

class BuildsResource(HtmlResource):
    addSlash = True

    def __init__(self, builder_status, builder_control):
        HtmlResource.__init__(self)
        self.builder_status = builder_status
        self.builder_control = builder_control

    def getChild(self, path, req):
        try:
            num = int(path)
        except ValueError:
            num = None
        if num is not None:
            build_status = self.builder_status.getBuild(num)
            if build_status:
                build_control = None
                if self.builder_control:
                    builder_control = self.builder_control.getBuild(num)
                return StatusResourceBuild(build_status, build_control,
                                           self.builder_control)

        return HtmlResource.getChild(self, path, req)
