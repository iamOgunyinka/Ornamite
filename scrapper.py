import requests, os
from BeautifulSoup import BeautifulSoup

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
        
    def __repr__(self):
        return '\t\t\t<DlLink -> {} : {}>'.format(self.download_type, self.download_link)

class TvEpisode():
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

    def __repr__(self):
        return '\t\t<TvEpisode -> title: {}, links: {}>'.format(self.title, self.download_links)


class TvSeason():
    def __add_episode__(self, episode):
        if not isinstance(episode, TvEpisode):
            raise ValueError('{} is not a valid episode instance'.format(episode))
        if not episode in frozenset(self.episodes):
            self.episodes.append(episode)

    def __init__(self, title, page_link):
        self.title = title
        self.page_link = page_link
        self.episodes = []
    
    def add_episode(self, episode, *episodes):
        print 'Adding new episode'
        self.__add_episode__(episode)
        for new_episode in episodes:
            self.__add_episode__(new_episode)
    
    def __repr__(self):
        number_of_episodes = len(self.episodes)
        episodes_info = ''
        for index in range(0, number_of_episodes):
            episodes_info += str(self.episodes[index]) + ('\n' if index != number_of_episodes-1 else '') 
        return '\t<TvSeason: {}, Link: {}, Episodes:\n{}\n>'.format(self.title, self.page_link, episodes_info)


class TvTitle():
    def __init__(self, title):
        self.title = title
        self.seasons = []

    def add_season(self,season):
        if isinstance(season, TvSeason):
            self.seasons.append(season)
        else:
            raise ValueError('Invalid season')
            
    def __repr__(self):
        seasons_info = ''
        number_of_seasons = len(self.seasons)
        for index in range(0,number_of_seasons):
            seasons_info += str(self.seasons[index]) + ('\n' if index != number_of_seasons-1 else '') 
        return '<TvTitle: {}, Number of seasons: {}, Seasons:\n{}>\n\n'.format(self.title, number_of_seasons, seasons_info)


def get_data_or_return(link, callback_on_failure=None):
    try:
        rsp = requests.get(link)
    except Exception as e:
        print 'An exception occured: {}'.format(e)
        if callback_on_failure is not None:
            callback_on_failure()
    if not rsp.ok:
        print 'Invalid response gotten from main page, code: {}'.format(response.status_code)
        if callback_on_failure is not None:
            callback_on_failure()
    return rsp


def main_page_scrapper():
    rsp = get_data_or_return(main_url, lambda: exit(-1))
    visited_sites[main_url] = True
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
            new_episode = TvEpisode(episode_link, episode_name)
            add_episode_dlinks(episode_link, new_episode)
            season.add_episode(new_episode)
            return
    print 'We could not find the season for the movie'


def append_season(ahref, *args, **kw):
    tv_title = kw.get('title').lower()
    title = tv_series.get(tv_title)
    if title is None:
        title = TvTitle(kw.get('title'))
    seasons_name = ahref.string.rstrip()
    seasons_link = ahref.attrs[0][1]
    print 'Adding {} to {}'.format(seasons_name, tv_title)
    title.add_season(TvSeason(seasons_name, seasons_link))
    tv_series[tv_title]=title
    list_link_series(seasons_link, append_episode, title=tv_title, season=seasons_name)


def list_tv_seasons(tv_title, page_link):
    list_link_series(page_link, append_season, title=tv_title)


if __name__ == '__main__':
    main_page_scrapper()
    for links in visiting_links:
        list_link_series(links, store_tv_series)
    for tv_key in direct_page_links:
        list_tv_seasons(tv_key, direct_page_links[tv_key])
    my_file = open('./tv_shows.txt', 'w')
    for series in tv_series:
        my_file.write(tv_series.get(series).__repr__())
    my_file.close()
