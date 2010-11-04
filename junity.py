#!/usr/bin/env python


import os.path
import re
import sys
import xml.dom.minidom


class TestVerdict(object):
    SUCCESS = 0
    FAILURE = 1
    ERROR = 2


class TestCase(object):

    def __init__(self, name, verdict):
        self.name = name
        self.verdict = verdict

    def to_xml(self):
        x = ""
        x += "<testcase name=\"" + self.name + "\""
        if self.verdict == TestVerdict.ERROR:
            x += "><error /></testcase>"
        elif self.verdict == TestVerdict.FAILURE:
            x += "><failure /></testcase>"
        else:
            x += " />"
        return x

    def __str__(self):
        return self.to_xml()


class TestSuiteError(object):

    def __init__(self, message):
        self.message = message

    def to_xml(self):
        x = ""
        x += "<error message=\"" + self.message + "\" />"
        return x

    def __str__(self):
        return self.to_xml()


class TestSuite(object):

    def __init__(self, name):
        self.name = name
        self.children = [] # TestCase or TestSuiteError

    def append(self, child):
        self.children.append(child)

    def to_xml(self):
        x = ""
        x += "<testsuite name=\"" + self.name + "\">"
        for child in self.children:
            x += child.to_xml()
        x += "</testsuite>"
        return x

    def __str__(self):
        return self.to_xml()


class TestSuites(object):

    def __init__(self, test_suites = None):
        self.test_suites = [] if test_suites is None else test_suites

    def append(self, test_suite):
        self.test_suites.append(test_suite)

    def extend(self, test_suites):
        self.test_suites.extend(test_suites.test_suites)

    def to_xml(self):
        x = ""
        x += "<testsuites>"
        for test_suite in self.test_suites:
            x += test_suite.to_xml()
        x += "</testsuites>"
        return x

    def __str__(self):
        return self.to_xml()


class FormatHandler(object):

    def accept(self, path, text):
        raise NotImplementedError

    def read(self, path, text):
        raise NotImplementedError


class BoostFormatHandler(FormatHandler):

    def accept(self, path, text):
        return text.find("<TestCase") != -1

    def read(self, path, text):
        document = parse_xml(path, text)
        test_suites = TestSuites()
        for element in document.getElementsByTagName("TestSuite"):
            test_suites.append(self.read_test_suite(path, element))
        return test_suites

    def read_test_suite(self, path, element):
        name = element.getAttribute("name")
        test_suite = TestSuite(name)
        for element in element.getElementsByTagName("TestCase"):
            test_suite.append(self.read_test_case(path, element))
        return test_suite

    def read_test_case(self, path, element):
        name = element.getAttribute("name")
        verdict = self.read_test_verdict(path, element)
        test_case = TestCase(name, verdict)
        return test_case

    def read_test_verdict(self, path, element):
        result = element.getAttribute("result")
        if result == "passed":
            verdict = TestVerdict.SUCCESS
        elif result == "failed":
            verdict = TestVerdict.FAILURE
        else:
            verdict = TestVerdict.ERROR
        return verdict


class JUnitFormatHandler(FormatHandler):

    def accept(self, path, text):
        return text.find("<testcase") != -1

    def read(self, path, text):
        document = parse_xml(path, text)
        test_suites = TestSuites()
        for element in document.getElementsByTagName("testsuite"):
            test_suites.append(self.read_test_suite(path, element))
        return test_suites

    def read_test_suite(self, path, element):
        name = element.getAttribute("name")
        test_suite = TestSuite(name)
        for element in element.getElementsByTagName("testcase"):
            test_suite.append(self.read_test_case(path, element))
        return test_suite

    def read_test_case(self, path, element):
        name = element.getAttribute("name")
        verdict = self.read_test_verdict(path, element)
        test_case = TestCase(name, verdict)
        return test_case

    def read_test_verdict(self, path, element):
        if len(element.getElementsByTagName("error")) > 0:
            verdict = TestVerdict.ERROR
        elif len(element.getElementsByTagName("failure")) > 0:
            verdict = TestVerdict.FAILURE
        else:
            verdict = TestVerdict.SUCCESS
        return verdict


class TitanFormatHandler(FormatHandler):

    VERDICT_STATISTICS = re.compile(r"""
                                    (?P<none>\d+)\ none
                                    \ \([^\)]+\),\ 
                                    (?P<pass>\d+)\ pass
                                    \ \([^\)]+\),\ 
                                    (?P<inconc>\d+)\ inconc
                                    \ \([^\)]+\),\ 
                                    (?P<fail>\d+)\ fail
                                    \ \([^\)]+\),\ 
                                    (?P<error>\d+)\ error
                                    \ \([^\)]+\).
                                    """, re.VERBOSE)
    
    def accept(self, path, text):
        return text.find("Verdict statistics") != -1

    def read(self, path, text):
        try:
            match = TitanFormatHandler.VERDICT_STATISTICS.search(text)
            nones = int(match.group("none"))
            passes = int(match.group("pass"))
            inconcs = int(match.group("inconc"))
            fails = int(match.group("fail"))
            errors = int(match.group("error"))
        except:
            raise FormatHandlerError(path, "This TITAN log file has invalid "
                                           "format.")
        return self.generate_test_suites(path, nones, passes, inconcs, fails,
                                         errors)

    def generate_test_suites(self, path, nones, passes, inconcs, fails,
                             errors):
        test_suite = TestSuite(os.path.basename(path))
        for num in range(nones):
            test_suite.append(TestCase("none-%d" % num, TestVerdict.FAILURE))
        for num in range(passes):
            test_suite.append(TestCase("pass-%d" % num, TestVerdict.SUCCESS))
        for num in range(inconcs):
            test_suite.append(TestCase("inconc-%d" % num, TestVerdict.ERROR))
        for num in range(fails):
            test_suite.append(TestCase("fail-%d" % num, TestVerdict.FAILURE))
        for num in range(errors):
            test_suite.append(TestCase("error-%d" % num, TestVerdict.ERROR))
        return TestSuites([ test_suite ])


HANDLERS = [ BoostFormatHandler(),
             JUnitFormatHandler(),
             TitanFormatHandler() ]


class FormatHandlerError(Exception):

    def __init__(self, path, message):
        self.test_suite = TestSuite(os.path.basename(path))
        self.test_suite.append(TestSuiteError(message))

    def format(self):
        return TestSuites([ self.test_suite ])


def parse_xml(path, text):
    try:
        return xml.dom.minidom.parseString(text)
    except:
        raise FormatHandlerError(path, "This XML file is not well-formed.")


def handle(path):
    try:
        text = open(path).read()
    except:
        raise FormatHandlerError(path, "This file cannot be read.")

    for handler in HANDLERS:
        if handler.accept(path, text):
            return handler.read(path, text)

    raise FormatHandlerError(path, "This file has unknown format.")


def main():
    if len(sys.argv) < 2:
        usage()

    test_suites = TestSuites()
    for arg in sys.argv[1:]:
        try:
            test_suites.extend(handle(arg))
        except FormatHandlerError, error:
            test_suites.extend(error.format())
    print test_suites


def usage():
    sys.exit("Usage: junity.py FILE [FILE ...]")


if __name__ == "__main__":
    main()
