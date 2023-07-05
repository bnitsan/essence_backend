import csv
import json

def export_session_to_csv(url: str, title: str, output: list, qa_list: list, path='data/export_csvs/temp.csv') -> None:
    '''
    data is a dict with keys 'subject' and 'content'
    We want CSVs to be rectangular, i.e. each row has the same number of columns.
    We therefore first run on the data to find the maximum number of columns.
    '''

    max_col = 2
    for palette in output:
        for d in palette['text']:
            key = d['key']
            val = d['value']
            if isinstance(val, list):
                max_col = max(max_col, len(val[0])+1)
        if len(qa_list) > 0:
            max_col = max(max_col, 3)
                
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Title', title]+['']*(max_col-2))
        
        for i, palette in enumerate(output):
            writer.writerow(['']*(max_col)) # writer.writerow(['Entry ' + str(i+1)]+['']*(max_col-1))
            writer.writerow([palette['title']]+['']*(max_col-1))
            writer.writerow(['URL', palette['url']]+['']*(max_col-2))
            text_output = palette['text']
            if isinstance(text_output, str):
                writer.writerow(['Summary', text_output]+['']*(max_col-2))
                writer.writerow(['']*max_col)
            # in case we have a "note" where text_output = [{'key': '', 'value': 'note...'}], we may want to print it differently; this commented block captures it; inactive
            #elif len(text_output) == 1 and 'key' in text_output[0] and text_output[0]['key'] == '':
            #    writer.writerow([text_output[0]['value']]+['']*(max_col-1))
            #    writer.writerow(['']*max_col)
            else:
                for d in text_output:
                    key = d['key']
                    val = d['value']
                    # if val is string, write it
                    if isinstance(val, str):
                        writer.writerow([key, val]+['']*(max_col-2))
                    # if val is list, write each element
                    elif isinstance(val, list):
                        writer.writerow([key] + val[0] +['']*(max_col-1-len(val[0])))
                        for v in val[1:]:
                            writer.writerow([''] + v + ['']*(max_col-1-len(val[0])))

        for j, qa in enumerate(qa_list):
            question, answer = qa[0], qa[1]
            if j == 0:
                writer.writerow(['Q&A']+[question, answer] + ['']*(max_col-3))
            else:
                writer.writerow(['']+[question, answer] + ['']*(max_col-3))
            
        writer.writerow(['']*max_col)


def export_divider_to_csv(data: dict, path='data/export_csvs/temp.csv') -> None:
    '''
    data is a dict with keys 'subject' and 'content'.
    We want CSVs to be rectangular, i.e. each row has the same number of columns.
    We therefore first run on the data to find the maximum number of columns.
    '''

    max_col = 3
    for session in data['content']:
        if isinstance(session['long_summary'], str):
            continue
        for entry in session['long_summary']:
            for d in entry['text']:
                key = d['key']
                val = d['value']
                if isinstance(val, list):
                    max_col = max(max_col, len(val[0])+2)
        if len(session['qa_list']) > 0:
            max_col = max(max_col, 4)
                
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['SUBJECT', data['subject']]+['']*(max_col-2))
        writer.writerow(['']*max_col)

        for i, session in enumerate(data['content']):
            writer.writerow(['Session ' + str(i+1), 'Title', session['title']]+['']*(max_col-3))
            # writer.writerow(['', 'URL', session['url']]+['']*(max_col-3))
            
            if isinstance(session['long_summary'], str):
                writer.writerow(['', 'Summary', session['long_summary']]+['']*(max_col-3))
                writer.writerow(['']*max_col)
                continue
            
            for j, palette in enumerate(session['long_summary']):
                writer.writerow(['']*max_col) # writer.writerow([''] + ['Entry ' + str(j+1)]+['']*(max_col-1))
                writer.writerow([''] + [palette['title']]+['']*(max_col-2))
                writer.writerow([''] + ['URL', palette['url']]+['']*(max_col-3))

                for d in palette['text']:
                    key = d['key']
                    val = d['value']
                    
                    # if val is string, write it
                    if isinstance(val, str):
                        writer.writerow(['', key, val]+['']*(max_col-3))
                    # if val is list, write each element
                    elif isinstance(val, list):
                        writer.writerow(['', key] + val[0] +['']*(max_col-2-len(val[0])))
                        for v in val[1:]:
                            writer.writerow(['', ''] + v + ['']*(max_col-2-len(val[0])))

            for j, qa in enumerate(session['qa_list']):
                question, answer = qa[0], qa[1]
                if j == 0:
                    writer.writerow(['', 'Q&A']+[question, answer] + ['']*(max_col-4))
                else:
                    writer.writerow(['', '']+[question, answer] + ['']*(max_col-4))
                
            writer.writerow(['']*max_col)

