import json
import datetime
import csv
import time
try:
    from urllib.request import urlopen, Request
except ImportError:
    from urllib2 import urlopen, Request

app_id = "<FILL IN>"
app_secret = "<FILL IN>"  # DO NOT SHARE WITH ANYONE!
group_id = "759985267390294"

REACTIONS_STATUS_START = '2016-02-24 00:00:00'

access_token = app_id + "|" + app_secret


def request_until_succeed(url):
    req = Request(url)
    success = False
    while success is False:
        try:
            response = urlopen(req)
            if response.getcode() == 200:
                success = True
        except Exception as e:
            print(e)
            time.sleep(5)

            print("Error for URL {}: {}".format(url, datetime.datetime.now()))
            print("Retrying.")

    return response.read()

# Needed to write tricky unicode correctly to csv


def unicode_decode(text):
    try:
        return text.encode('utf-8').decode()
    except UnicodeDecodeError:
        return text.encode('utf-8')


def getFacebookPageFeedData(page_id, access_token, num_statuses):

    # Construct the URL string; see http://stackoverflow.com/a/37239851 for
    # Reactions parameters
    base = "https://graph.facebook.com/v2.9"
    node = "/{}/feed".format(page_id)
    fields = "/?fields=message,link,created_time,type,name,id," + \
        "comments.limit(0).summary(true),shares,reactions" + \
        ".limit(0).summary(true),from"
    parameters = "&limit={}&access_token={}".format(num_statuses, access_token)
    url = base + node + fields + parameters

    # retrieve data
    data = json.loads(request_until_succeed(url))

    return data


def getReactionsForStatus(status_id, access_token):

    # See http://stackoverflow.com/a/37239851 for Reactions parameters
    # Reactions are only accessable at a single-post endpoint

    base = "https://graph.facebook.com/v2.9"
    node = "/{}".format(status_id)
    reactions = "/?fields=" \
        "reactions.type(LIKE).limit(0).summary(total_count).as(like)" \
        ",reactions.type(LOVE).limit(0).summary(total_count).as(love)" \
        ",reactions.type(WOW).limit(0).summary(total_count).as(wow)" \
        ",reactions.type(HAHA).limit(0).summary(total_count).as(haha)" \
        ",reactions.type(SAD).limit(0).summary(total_count).as(sad)" \
        ",reactions.type(ANGRY).limit(0).summary(total_count).as(angry)"
    parameters = "&access_token={}".format(access_token)
    url = base + node + reactions + parameters

    # retrieve data
    data = json.loads(request_until_succeed(url))

    return data


def processFacebookPageFeedStatus(status, access_token):

    # The status is now a Python dictionary, so for top-level items,
    # we can simply call the key.

    # Additionally, some items may not always exist,
    # so must check for existence first

    status_id = status['id']
    status_type = status['type']

    status_message = '' if 'message' not in status else \
        unicode_decode(status['message'])
    link_name = '' if 'name' not in status else \
        unicode_decode(status['name'])
    status_link = '' if 'link' not in status else \
        unicode_decode(status['link'])
    status_author = unicode_decode(status['from']['name'])

    # Time needs special care since a) it's in UTC and
    # b) it's not easy to use in statistical programs.

    status_published = datetime.datetime.strptime(
        status['created_time'], '%Y-%m-%dT%H:%M:%S+0000')
    status_published = status_published + datetime.timedelta(hours=-5)  # EST
    # best time format for spreadsheet programs:
    status_published = status_published.strftime('%Y-%m-%d %H:%M:%S')

    # Nested items require chaining dictionary keys.

    num_reactions = 0 if 'reactions' not in status else \
        status['reactions']['summary']['total_count']
    num_comments = 0 if 'comments' not in status else \
        status['comments']['summary']['total_count']
    num_shares = 0 if 'shares' not in status else \
        status['shares']['count']

    # Counts of each reaction separately; good for sentiment
    # Only check for reactions if past date of implementation:
    # http://newsroom.fb.com/news/2016/02/reactions-now-available-globally/

    reactions = getReactionsForStatus(status_id, access_token) \
        if status_published > REACTIONS_STATUS_START else {}

    num_likes = 0 if 'like' not in reactions else \
        reactions['like']['summary']['total_count']

    # Special case: Set number of Likes to Number of reactions for pre-reaction
    # statuses

    num_likes = num_reactions if status_published < REACTIONS_STATUS_START else \
        num_likes

    def get_num_total_reactions(reaction_type, reactions):
        if reaction_type not in reactions:
            return 0
        else:
            return reactions[reaction_type]['summary']['total_count']

    num_loves = get_num_total_reactions('love', reactions)
    num_wows = get_num_total_reactions('wow', reactions)
    num_hahas = get_num_total_reactions('haha', reactions)
    num_sads = get_num_total_reactions('sad', reactions)
    num_angrys = get_num_total_reactions('angry', reactions)

    # return a tuple of all processed data

    return (status_id, status_message, status_author, link_name, status_type,
            status_link, status_published, num_reactions, num_comments,
            num_shares,  num_likes, num_loves, num_wows, num_hahas, num_sads,
            num_angrys)


def scrapeFacebookPageFeedStatus(group_id, access_token):
    with open('{}_facebook_statuses.csv'.format(group_id), 'w') as file:
        w = csv.writer(file)
        w.writerow(["status_id", "status_message", "status_author", "link_name",
                    "status_type", "status_link", "status_published",
                    "num_reactions", "num_comments", "num_shares", "num_likes",
                    "num_loves", "num_wows", "num_hahas", "num_sads", "num_angrys"])

        has_next_page = True
        num_processed = 0   # keep a count on how many we've processed
        scrape_starttime = datetime.datetime.now()

        print("Scraping {} Facebook Group: {}\n".format(
            group_id, scrape_starttime))

        statuses = getFacebookPageFeedData(group_id, access_token, 100)

        while has_next_page:
            for status in statuses['data']:

                # Ensure it is a status with the expected metadata
                if 'reactions' in status:
                    w.writerow(processFacebookPageFeedStatus(status,
                                                             access_token))

                # output progress occasionally to make sure code is not
                # stalling
                num_processed += 1
                if num_processed % 100 == 0:
                    print("{} Statuses Processed: {}".format
                          (num_processed, datetime.datetime.now()))

            # if there is no next page, we're done.
            if 'paging' in statuses.keys():
                statuses = json.loads(request_until_succeed(
                    statuses['paging']['next']))
            else:
                has_next_page = False

        print("\nDone!\n%s Statuses Processed in {}".format(
              (num_processed, datetime.datetime.now() - scrape_starttime)))


if __name__ == '__main__':
    scrapeFacebookPageFeedStatus(group_id, access_token)


# The CSV can be opened in all major statistical programs. Have fun! :)
