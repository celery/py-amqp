#!/usr/bin/env python
"""
Utility for parsing an AMQP XML spec file
and generating a Python module skeleton.

This is a fairly ugly program, but it's only intended
to be run once.

2007-11-10 Barry Pederson <bp@barryp.org>

"""
import sys
import textwrap
from optparse import OptionParser
from xml.etree import ElementTree

domains = {}

def _fixup_method_name(class_element, method_element):
    if class_element.attrib['name'] != class_element.attrib['handler']:
        prefix = '%s_' % class_element.attrib['name']
    else:
        prefix = ''
    return ('%s%s' % (prefix, method_element.attrib['name'])).replace('-', '_')

def _fixup_field_name(field_element):
    result = field_element.attrib['name'].replace(' ', '_')
    if result == 'global':
        result = 'a_global'
    return result

def _field_type(field_element):
    if 'type' in field_element.attrib:
        return field_element.attrib['type']
    if 'domain' in field_element.attrib:
        return domains[field_element.attrib['domain']]


def _reindent(s, indent):
    s = textwrap.dedent(s)
    s = s.split('\n')
    s = [x.rstrip() for x in s]
    while s and (not s[0]):
        s = s[1:]
    while s and (not s[-1]):
        s = s[:-1]
    s = [indent + x for x in s]
    return '\n'.join(s)


def generate_docstr(element, indent='', wrap=None):
    docs = element.findall('doc')
    if not docs:
        return None

    result = []

    if wrap is not None:
        result.append(wrap)

    for d in docs:
        if 'name' in d.attrib:
            result.append(indent + d.attrib['name'].upper() + ':')
            result.append(indent)
            extra_indent = '    '
        else:
            extra_indent = ''
        result.append(_reindent(d.text, indent + extra_indent))
        result.append(indent)
    if wrap is not None:
        result.append(wrap)
    return '\n'.join(result) + '\n'


def generate_module(spec, out):
    """
    Given an AMQP spec parsed into an xml.etree.ElemenTree,
    and a file-like 'out' object to write to, generate
    the skeleton of a Python module.

    """
    for domain in spec.findall('domain'):
        domains[domain.attrib['name']] = domain.attrib['type']

    for amqp_class in spec.findall('class'):
        if amqp_class.attrib['handler'] == amqp_class.attrib['name']:
            out.write('class %s(object):\n' % amqp_class.attrib['name'].capitalize())
            s = generate_docstr(amqp_class, '    ', '    """')
            if s:
                out.write(s)
        else:
            out.write('    #############\n')
            out.write('    #\n')
            out.write('    #  %s\n' % amqp_class.attrib['name'].capitalize())
            out.write('    #\n')
            s = generate_docstr(amqp_class, '    # ', '    # ')
            if s:
                out.write(s)
            out.write('\n')

        for amqp_method in amqp_class.findall('method'):
            fields = amqp_method.findall('field')
            fieldnames = [_fixup_field_name(x) for x in fields]
            chassis = [x.attrib['name'] for x in amqp_method.findall('chassis')]
            if 'server' in chassis:
                params = ['self']
                if 'content' in amqp_method.attrib:
                    params.append('msg')
                out.write('    def %s(%s):\n' %
                    (_fixup_method_name(amqp_class, amqp_method), ', '.join(params + fieldnames)))
                s = generate_docstr(amqp_method, '        ', '        """')
                if s:
                    out.write(s)
                out.write('        args = _AMQPWriter()\n')
                for f in fields:
                    out.write('        args.write_%s(%s)\n' % (_field_type(f), _fixup_field_name(f)))

                if amqp_class.attrib['name'] == 'connection':
                    out.write('        self.send_method_frame(0, %s, %s, args.getvalue())\n' % (amqp_class.attrib['index'], amqp_method.attrib['index']))
                    if 'synchronous' in amqp_method.attrib:
                        out.write('        return self.wait()\n')
                else:
                    out.write('        self.send_method_frame(%s, %s, args.getvalue())\n' % (amqp_class.attrib['index'], amqp_method.attrib['index']))
                    if 'synchronous' in amqp_method.attrib:
                        out.write('        return self.connection.wait()\n')
                out.write('\n\n')

            if 'client' in chassis:
                out.write('    def _%s(self, args):\n' % _fixup_method_name(amqp_class, amqp_method))
                s = generate_docstr(amqp_method, '        ', '        """')
                if s:
                    out.write(s)
                need_pass = True
                for f in fields:
                    out.write('        %s = args.read_%s()\n' % (_fixup_field_name(f), _field_type(f)))
                    need_pass = False
                if 'content' in amqp_method.attrib:
                    out.write('        msg = self.connection.receive_content()\n')
                    need_pass = False
                if need_pass:
                    out.write('        pass\n')
                out.write('\n\n')

    out.write('_METHOD_MAP = {\n')
    for amqp_class in spec.findall('class'):
        print amqp_class.attrib
#        for chassis in amqp_class.findall('chassis'):
#            print '  ', chassis.attrib
        for amqp_method in amqp_class.findall('method'):
#            print '  ', amqp_method.attrib
#            for chassis in amqp_method.findall('chassis'):
#                print '      ', chassis.attrib
            chassis = [x.attrib['name'] for x in amqp_method.findall('chassis')]
            if 'client' in chassis:
                out.write("    (%s, %s): (%s, '_%s'),\n" % (
                    amqp_class.attrib['index'],
                    amqp_method.attrib['index'],
                    amqp_class.attrib['handler'].capitalize(),
                    _fixup_method_name(amqp_class, amqp_method)))
    out.write('}\n')


def main(argv=None):
    if argv is None:
        argv = sys.argv

    if len(argv) < 2:
        print 'Usage: %s <amqp-spec> [<output-file>]' % argv[0]
        return 1

    spec = ElementTree.parse(argv[1])
    if len(argv) < 3:
        out = sys.stdout
    else:
        out = open(argv[2], 'w')

    generate_module(spec, out)

if __name__ == '__main__':
    sys.exit(main())
