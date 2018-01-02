import requests, os, json
from BeautifulSoup import BeautifulSoup
from threading import Thread


visited_sites = {}
visiting_links = []
all_series = []
direct_page_links = {}
tv_series = {}

main_url = os.environ.get('MAIN_URL')

class DlLink():
    def __init__(self, download_type, download_link):
        self.download_type = download_type
        self.download_link = download_link
    
    def __cmp__(self, y):
        return self.__eq__(y)

    def __hash__(self):
        return self.download_type.__hash__()
    
    def __eq__(self, another_dl_link):
        return self.download_type == another_dl_link.download_type # and self.download_link == another_dl_link.download_link
        
    def to_object(self):
        return {'type': self.download_type, 'link': self.download_link}

class ShowEpisode():
    def __init__(self, page_link, opt_title=None):
        self.link = page_link
        self.title = opt_title
        self.download_links = []
    
    def __hash__(self):
        return self.title.__hash__()
        
    def __cmp__(self,y):
        return self.__eq__(y)
    
    def __eq__(self, another_episode):
        return self.title == another_episode.title

    def add_download_link(self, download_link):
        if download_link is not None:
            if not download_link in frozenset(self.download_links):
                self.download_links.append(download_link)
                
    def to_object(self):
        return {'title': self.title, 'page_link': self.link, 'dl_links': [dl.to_object() for dl in self.download_links] }


class ShowSeason():
    def __add_episode__(self, episode):
        if not isinstance(episode, ShowEpisode):
            raise ValueError('{} is not a valid episode instance'.format(episode))
        if not episode in frozenset(self.episodes):
            self.episodes.append(episode)

    def __init__(self, title, page_link):
        self.title = title
        self.page_link = page_link
        self.episodes = []
    
    def add_episode(self, episode, *episodes):
        self.__add_episode__(episode)
        for new_episode in episodes:
            self.__add_episode__(new_episode)
    
    def to_object(self):
        return { 'title': self.title, 'page_link': self.page_link, 'episodes': [ep.to_object() for ep in self.episodes] }

class ShowTitle():
    def __init__(self, title):
        self.title = title
        self.seasons = []

    def add_season(self,season):
        if isinstance(season, ShowSeason):
            self.seasons.append(season)
        else:
            raise ValueError('Invalid season')
            
    def to_object(self):
        return {'name': self.title, 'seasons': [season.to_object() for season in self.seasons]}
    
    def __repr__(self):
        return json.dumps(self.to_object())

def get_data_or_return(link, callback_on_failure=None):
    try:
        rsp = requests.get(link)
    except Exception as e:
        print 'An exception occured: {}'.format(e)
        if callback_on_failure is not None:
            callback_on_failure()
        return None
    if not rsp.ok:
        print 'Invalid response gotten from main page, code: {}'.format(response.status_code)
        if callback_on_failure is not None:
            callback_on_failure()
            return None
    return rsp


def main_page_scrapper():
    rsp = get_data_or_return(main_url, None)
    visited_sites[main_url] = True
    if rsp is None:
        return
    soup = BeautifulSoup(rsp.content)
    all_series_links = soup.findAll('div', attrs={'class': 'series_set'})
    if len(all_series_links) == 0:
        print 'No series found'
        exit(0)
    for series_link in all_series_links:
        link = series_link.findAll('a')
        for l in link:
            for attribute in l.attrs:
                if len(attribute) == 2 and attribute[0] == u'href':
                    visiting_links.append(attribute[1])


def list_link_series(link, post_data_callback, *callback_args, **callback_kw ):
    if visited_sites.get(link) is not None:
        return
    visited_sites[link] = True
    network_response = get_data_or_return(link)
    if network_response is None: 
        return
    parsed_data = BeautifulSoup(network_response.content)
    data_list = parsed_data.findAll('div', attrs={'class': 'data'})
    for data_item in data_list:
        ahrefs = data_item.findAll('a')
        for ahref in ahrefs:
            post_data_callback(ahref, *callback_args, **callback_kw)
    next_pages_info = parsed_data.findAll('div', attrs={'class': 'pagination'})
    for page in next_pages_info:
        next_pages = page.findAll('a')
        for next_page in next_pages:
            page_attributes = next_page.attrs
            for page_attrib in page_attributes:
                if len(page_attrib) >= 2 and page_attrib[0] == 'href':
                    list_link_series(page_attrib[1], post_data_callback, *callback_args, **callback_kw)


def store_tv_series(ahref, *args, **kwargs):
    tv_title = ahref.string.rstrip()
    tv_page_link = ahref.attrs[0][1]
    direct_page_links[tv_title] = tv_page_link


def dl_link_extractor(ahref_object, *args, **kwargs):
    download_link = ahref_object.attrs[0][1]
    if download_link == '#':
        return
    download_type = ahref_object.string.rstrip()
    kwargs['episode'].add_download_link(DlLink(download_type, download_link))


def add_episode_dlinks(episode_link, current_episode):
    list_link_series(episode_link, dl_link_extractor, episode=current_episode)


def append_episode(ahref, *args, **kwargs):
    tv_title = kwargs.get('title')
    season_name = kwargs.get('season')
    current_series = tv_series.get(tv_title)
    episode_link = ahref.attrs[0][1]
    episode_name = ahref.string.rstrip()
    for season in current_series.seasons:
        if season_name == season.title:
            new_episode = ShowEpisode(episode_link, episode_name)
            add_episode_dlinks(episode_link, new_episode)
            season.add_episode(new_episode)
            return
    print 'We could not find the season for the movie'


def append_season(ahref, *args, **kw):
    tv_title = kw.get('title').lower()
    title = tv_series.get(tv_title)
    if title is None:
        title = ShowTitle(kw.get('title'))
    seasons_name = ahref.string.rstrip()
    seasons_link = ahref.attrs[0][1]
    print 'Adding {} to {}'.format(seasons_name, tv_title)
    title.add_season(ShowSeason(seasons_name, seasons_link))
    tv_series[tv_title]=title
    list_link_series(seasons_link, append_episode, title=tv_title, season=seasons_name)


def list_tv_seasons(tv_title, page_link):
    list_link_series(page_link, append_season, title=tv_title)


if __name__ == '__main__':
    main_page_scrapper()
    #~ list_link_series(visiting_links[0], store_tv_series)
    #~ tv_key = direct_page_links.keys()[0]
    #~ list_tv_seasons(tv_key, direct_page_links[tv_key])
    thread_list = []
    for links in visiting_links:
        list_link_series(links, store_tv_series)
    for tv_key in direct_page_links:
        new_thread = Thread(target=list_tv_seasons, args=[tv_key, direct_page_links[tv_key]])
        thread_list.append(new_thread)
        new_thread.start()
        #~ list_tv_seasons(tv_key, direct_page_links[tv_key])
    for my_thread in thread_list:
        if my_thread.is_alive():
            my_thread.join()
    with open('./tv_shows.txt', 'w') as my_file:
        s = []
        for series in tv_series:
            s.append(tv_series[series].to_object())
        my_file.write(json.dumps(s, indent=2, separators=(',', ': ')))
