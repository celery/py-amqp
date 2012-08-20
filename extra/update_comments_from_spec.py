import sys, os
import re

default_source_file = os.path.join(os.path.dirname(__file__), '../amqp/channel.py')  

def update_comments(comments_file, impl_file, result_file):
    text_file = open(impl_file, 'r')
    source = text_file.read()
    
    comments = get_comments(comments_file)
    for def_name, comment in comments.items():
        source = repalce_comment_per_def(source, result_file, def_name, comment)
    
    new_file = open(result_file, 'w+')
    new_file.write(source)
    
    
def get_comments(filename):
    text_file = open(filename, 'r')
    whole_source = text_file.read()
    comments = {}
    
    regex = '(?P<methodsig>def\s+(?P<mname>[a-zA-Z0-9_]+)\(.*?\):\n+\s+""")(?P<comment>.*?)(?=""")' 
    all_matches =  re.finditer(regex, whole_source, re.MULTILINE| re.DOTALL)
    for match in all_matches:
        comments[match.group('mname')] = match.group('comment')
        #print 'method: %s \ncomment: %s' %(match.group('mname'), match.group('comment'))
           
    return comments
    
def repalce_comment_per_def(source, result_file, def_name, new_comment):
    
    regex = '(?P<methodsig>def\s+' + def_name + '\(.*?\):\n+\s+""".*?\n).*?(?=""")' 
    #print 'method and comment:' + def_name + new_comment
    result =  re.sub(regex, '\g<methodsig>' + new_comment, source, 0, re.MULTILINE| re.DOTALL)
    return result

def main(argv=None):   
    if argv is None:
        argv = sys.argv
    
    if len(argv) < 3:
        print 'Usage: %s <comments-file> <output-file> [<source-file>]' % argv[0]
        return 1

    impl_file = default_source_file
    if len(argv)>= 4:
        impl_file = argv[3]
        
    update_comments(argv[1], impl_file, argv[2])
    
if __name__ == '__main__':
    sys.exit(main())