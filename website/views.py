import numpy as np
import os, sys
import requests

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Max
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template import loader
from django.views.decorators.csrf import csrf_protect

sys.path.append(os.path.join(
    os.path.dirname(__file__), "..", "tellina_learning_module"))

from bashlint import data_tools

#from website.models import NL, Command, NLRequest, Translation, Vote, User, Comment

WEBSITE_DEVELOP = False
CACHE_TRANSLATIONS = False

from website.models import NL, Command, NLRequest, URL, Translation, Vote, User
from website.utils import get_tag, get_nl, get_command
from website import functions
from website.cmd2html import tokens2html

from website.scripts.db_changes import *
from website.scripts.export_pairs import *
# load_urls(os.path.join(os.path.dirname(__file__), 'data', 'stackoverflow.urls'))
# load_commands_in_url(
#     '/home/xilin/Projects/tellina/learning_module/data/stackoverflow/stackoverflow.sqlite3')
# populate_command_tags()
# populate_command_template()
# populate_tag_commands()
# populate_tag_annotations()
# create_notifications()
# ast = data_tools.bash_parser("cd $(find . -name Subscription.java | xargs dirname)")
# data_tools.pretty_print(ast)
# print(data_tools.get_utilities(ast))
gen_annotation_check_sheet('.')

if not WEBSITE_DEVELOP:
    from website.backend_interface import translate_fun


def ip_address_required(f):
    @functions.wraps(f)
    def g(request, *args, **kwargs):
        try:
            ip_address = request.COOKIES['ip_address']
        except KeyError:
            # redirect to home page if no ip address is captured
            return index(request)
        return f(request, *args, ip_address=ip_address, **kwargs)

    return g

###
if not WEBSITE_DEVELOP:
    from website.helper_interface import translate_fun


@csrf_protect
@ip_address_required
def translate(request, ip_address):
    template = loader.get_template('translator/translate.html')
    if request.method == 'POST':
        request_str = request.POST.get('request_str')
    else:
        request_str = request.GET.get('request_str')

    if not request_str or not request_str.strip():
        return redirect('/')

    while request_str.endswith('/'):
        request_str = request_str[:-1]

    # check if the natural language request is in the database
    nl = get_nl(request_str)

    trans_list = []
    html_strs = []

    if CACHE_TRANSLATIONS and \
            Translation.objects.filter(nl=nl).exists():
        # model translations exist
        cached_trans = Translation.objects.filter(nl=nl)
        for trans in cached_trans:
            pred_tree = data_tools.bash_parser(trans.pred_cmd)
            if pred_tree is not None:
                trans_list.append(trans)
                html_str = tokens2html(pred_tree)
                html_strs.append(html_str)

    # check if the user is in the database
    try:
        user = User.objects.get(ip_address=ip_address)
    except ObjectDoesNotExist:
        if ip_address == '123.456.789.012':
            organization = ''
            city = '--'
            region = '--'
            country = '--'
        else:
            r = requests.get('http://ipinfo.io/{}/json'.format(ip_address))
            organization = '' if r.json()['org'] is None else r.json()['org']
            city = '--' if r.json()['city'] is None else r.json()['city']
            region = '--' if r.json()['region'] is None else r.json()['region']
            country = '--' if r.json()['country'] is None else r.json()['country']
        user = User.objects.create(
            ip_address=ip_address,
            organization=organization,
            city=city,
            region=region,
            country=country
        )

    # save the natural language request issued by this IP Address
    nl_request = NLRequest.objects.create(nl=nl, user=user)

    if not trans_list:
        if not WEBSITE_DEVELOP:
            # call learning model and store the translations
            batch_outputs, output_logits = translate_fun(request_str)

            if batch_outputs:
                top_k_predictions = batch_outputs[0]
                top_k_scores = output_logits[0]

                for i in range(len(top_k_predictions)):
                    pred_tree, pred_cmd = top_k_predictions[i]
                    score = top_k_scores[i]
                    cmd = get_command(pred_cmd)
                    trans_set = Translation.objects.filter(nl=nl, pred_cmd=cmd)
                    if not trans_set.exists():
                        trans = Translation.objects.create(
                            nl=nl, pred_cmd=cmd, score=score)
                    else:
                        for trans in trans_set:
                            break
                        trans.score = score
                        trans.save()
                    trans_list.append(trans)
                    html_str = tokens2html(pred_tree)
                    html_strs.append(html_str)

    translation_list = []
    for trans, html_str in zip(trans_list, html_strs):
        upvoted, downvoted, starred = "", "", ""
        if Vote.objects.filter(translation=trans, ip_address=ip_address).exists():
            v = Vote.objects.get(translation=trans, ip_address=ip_address)
            upvoted = 1 if v.upvoted else ""
            downvoted = 1 if v.downvoted else ""
            starred = 1 if v.starred else ""
        translation_list.append((trans, upvoted, downvoted, starred,
                                 trans.pred_cmd.str.replace('\\', '\\\\'), html_str))

    # sort translation_list based on voting results
    translation_list.sort(
        key=lambda x: x[0].num_votes + x[0].score, reverse=True)
    # get comment of each translation
    trans_id_list = [trans_object[0].id for trans_object in translation_list]
    comment_list = get_comment(trans_id_list)
    context = {
        'nl_request': nl_request,
        'trans_list': translation_list,
        'comment_list': comment_list
    }
    return HttpResponse(template.render(context, request))


# @ip_address_required
# def vote(request, ip_address):
#     id = request.GET['id']
#     upvoted = request.GET['upvoted']
#     downvoted = request.GET['downvoted']
#     starred = request.GET['starred']
#
#     translation = Translation.objects.get(id=id)
#
#     vote_query = Vote.objects.filter(translation=translation, ip_address=ip_address)
#     # store voting record in the DB
#     if upvoted == 'true' or downvoted == 'true' or starred == 'true':
#         if vote_query.exists():
#             vote = Vote.objects.get(translation=translation, ip_address=ip_address)
#             if upvoted == 'true' and not vote.upvoted:
#                 translation.num_upvotes += 1
#             if downvoted == 'true' and not vote.downvoted:
#                 translation.num_downvotes += 1
#             if starred == 'true' and not vote.starred:
#                 translation.num_stars += 1
#             if upvoted == 'false' and vote.upvoted:
#                 translation.num_upvotes -= 1
#             if downvoted == 'false' and vote.downvoted:
#                 translation.num_downvotes -= 1
#             if starred == 'false' and vote.starred:
#                 translation.num_stars -= 1
#             vote.upvoted = (upvoted == 'true')
#             vote.downvoted = (downvoted == 'true')
#             vote.starred = (starred == 'true')
#             vote.save()
#         else:
#             Vote.objects.create(
#                 translation=translation, ip_address=ip_address,
#                 upvoted=(upvoted == 'true'),
#                 downvoted=(downvoted == 'true'),
#                 starred=(starred == 'true')
#             )
#             if upvoted == 'true':
#                 translation.num_upvotes += 1
#             if downvoted == 'true':
#                 translation.num_downvotes += 1
#             if starred == 'true':
#                 translation.num_stars += 1
#     else:
#         if vote_query.exists():
#             vote = Vote.objects.get(translation=translation, ip_address=ip_address)
#             if vote.upvoted == 'true':
#                 translation.num_upvotes -= 1
#             if vote.downvoted == 'true':
#                 translation.num_downvotes -= 1
#             if vote.starred == 'true':
#                 translation.num_stars -= 1
#             vote.delete();
#
#     translation.save()
#
#     return HttpResponse()

@ip_address_required
def vote(request, ip_address):
    nlrequest_id = request.GET['id']
    upvoted = request.GET['upvoted']
    downvoted = request.GET['downvoted']
    starred = request.GET['starred']

    user_request = NLRequest.objects.get(id=nlrequest_id)

    vote_query = Vote.objects.filter(request=user_request, ip_address=ip_address)
    # store voting record in the DB
    if upvoted == 'true' or downvoted == 'true' or starred == 'true':
        if vote_query.exists():
            vote_object = Vote.objects.get(request=user_request, ip_address=ip_address)
            vote_object.upvoted = (upvoted == 'true')
            vote_object.downvoted = (downvoted == 'true')
            vote_object.starred = (starred == 'true')
            vote_object.save()
        else:
            Vote.objects.create(
                request=user_request,
                ip_address=ip_address,
                upvoted=(upvoted == 'true'),
                downvoted=(downvoted == 'true'),
                starred=(starred == 'true')
            )
    # if Vote.objects.filter(
    #         translation=translation, ip_address=ip_address).exists():
    #     vote = Vote.objects.get(translation=translation, ip_address=ip_address)
    #     if upvoted == 'true' and not vote.upvoted:
    #         translation.num_upvotes += 1
    #     if downvoted == 'true' and not vote.downvoted:
    #         translation.num_downvotes += 1
    #     if starred == 'true' and not vote.starred:
    #         translation.num_stars += 1
    #     if upvoted == 'false' and vote.upvoted:
    #         translation.num_upvotes -= 1
    #     if downvoted == 'false' and vote.downvoted:
    #         translation.num_downvotes -= 1
    #     if starred == 'false' and vote.starred:
    #         translation.num_stars -= 1
    #     vote.upvoted = (upvoted == 'true')
    #     vote.downvoted = (downvoted == 'true')
    #     vote.starred = (starred == 'true')
    #     vote.save()
    else:
        if vote_query.exists():
            vote_object = Vote.objects.get(request=user_request, ip_address=ip_address)
            vote_object.delete()

    return HttpResponse()


@ip_address_required
def check_vote(request, ip_address):
    user_id = request.GET['id']

    user_request = NLRequest.objects.get(id=user_id)

    vote_query = Vote.objects.filter(request=user_request, ip_address=ip_address)

    if vote_query.exists():
        vote_object = Vote.objects.get(request=user_request, ip_address=ip_address)
        if vote_object.upvoted:
            return HttpResponse("up")
        if vote_object.downvoted:
            return HttpResponse("down")
        if vote_object.starred:
            return HttpResponse("star")
        return HttpResponse("error")
    else:
        return HttpResponse("false")


@ip_address_required
def leave_comment(request, ip_address):
    translation_id = request.POST['translation_id']
    user_id = request.POST['user_id']
    content = request.POST['content']


def get_comment(translation_ids):
    comments = {}
    for translation_id in translation_ids:
        comment_list = Comment.objects.filter(idtranslation=translation_id)
        if comment_list.exists():
            comments[translation_id] = comment_list
    return comments


def remember_ip_address(request):
    ip_address = request.GET['ip_address']
    resp = HttpResponse()
    resp.set_cookie('ip_address', ip_address)
    return resp


def index(request):
    template = loader.get_template('translator/index.html')
    context = {
        'example_request_list': example_requests_with_translations(),
        'latest_request_list': latest_requests_with_translations()
    }
    return HttpResponse(template.render(context, request))

def example_requests_with_translations():
    example_requests_with_translations = []
    example_request_list = [
        'remove all pdfs in my current directory',
        'delete all *.txt files in "myDir/"',
        'list files in "myDir/" that have been modified within 24 hours',
        'find all files named "test*.cpp" and move them to "project/code/"',
        'find all files larger than a gigabyte in the current folder',
        'find all png files larger than 50M that were last modified more than 30 days ago'
    ]

    for request_str in example_request_list:
        nl = get_nl(request_str)
        if Translation.objects.filter(nl__str=request_str).exists():
            translations = Translation.objects.filter(nl__str=request_str)
            max_score = translations.aggregate(Max('score'))['score__max']
            for top_translation in Translation.objects.filter(
                    nl__str=request_str, score=max_score):
                break
            top_translation = top_translation.pred_cmd.str
        else:
            # Compute the translations on the fly
            if not WEBSITE_DEVELOP:
                # call learning model and store the translations
                batch_outputs, output_logits = translate_fun(request_str)
                max_score = -np.inf
                top_translation = ''
                if batch_outputs:
                    top_k_predictions = batch_outputs[0]
                    top_k_scores = output_logits[0]
                    for i in range(len(top_k_predictions)):
                        pred_tree, pred_cmd = top_k_predictions[i]
                        score = top_k_scores[i]
                        if score > max_score:
                            max_score = score
                            top_translation = pred_cmd
                        cmd = get_command(pred_cmd)
                        Translation.objects.create(
                            nl=nl, pred_cmd=cmd, score=score)
            else:
                top_translation = 'No translation available.'
        example_requests_with_translations.append((nl, top_translation))

    return example_requests_with_translations


def latest_requests_with_translations():
    latest_requests_with_translations_query = []
    max_num_translation = 0

    for request in NLRequest.objects.order_by('-submission_time'):
        translations = Translation.objects.filter(nl=request.nl)
        if translations:
            max_score = translations.aggregate(Max('score'))['score__max']
            for top_translation in Translation.objects.filter(
                    nl=request.nl, score=max_score):
                break
            top_translation = top_translation.pred_cmd.str
        else:
            top_translation = 'No translation available.'
        latest_requests_with_translations_query.append((request, request.id, top_translation))
        max_num_translation += 1
        if max_num_translation % 20 == 0:
            break

    return latest_requests_with_translations_query


def info(request):
    template = loader.get_template('translator/info.html')
    context = {}
    return HttpResponse(template.render(context, request))
