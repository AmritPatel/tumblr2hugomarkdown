#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pytumblr
from datetime import datetime # for strptime
import re
import os
import codecs
import argparse
import hashlib # for image URL->path hashing
import urllib2 # for image downloading
import html2text # to convert body HTML to Markdown

def processPostBodyForImages(postBody, imagesPath, imagesUrlPath):
	tumblrImageUrl = re.compile(r"https?://[0-z.]+tumblr\.com/[0-z_/]+(\.jpe?g|\.png|\.gif)")

	while True:
		imageMatch = re.search(tumblrImageUrl, postBody)
		if not imageMatch:
			break

		concreteImageUrl = imageMatch.group(0)
		concreteImageExtension = imageMatch.group(1)
		imageHash = hashlib.sha256(concreteImageUrl).hexdigest()

		# Create the image folder if it does not exist
		if not os.path.exists(imagesPath):
			os.makedirs(imagesPath)

		concreteImagePath = os.path.join(imagesPath, imageHash + concreteImageExtension)
		imageOutputUrlPath = os.path.join(imagesUrlPath, imageHash + concreteImageExtension)

		# Assumes that all images are downloaded in full by httpclient, does not check for file integrity
		if os.path.exists(concreteImagePath):
			# This image was already downloaded, so just replace the URL in body
			postBody = postBody.replace(concreteImageUrl, imageOutputUrlPath)
			print "Found image url", concreteImageUrl, "already downloaded to path", concreteImagePath
		else:
			# Download the image and then replace the URL in body
			imageContent = urllib2.urlopen(concreteImageUrl).read()
			f = open(concreteImagePath, 'wb')
			f.write(imageContent)
			f.close()

			postBody = postBody.replace(concreteImageUrl, imageOutputUrlPath)
			print "Downloaded image url", concreteImageUrl, "to path", concreteImagePath

	return postBody

def downloader(apiKey, host, postsPath, downloadImages, imagesPath, imagesUrlPath, drafts):
	# Authenticate via API Key
	client = pytumblr.TumblrRestClient(apiKey)

	# http://www.tumblr.com/docs/en/api/v2#posts

	# Make the request
	processed = 0
	total_posts = 1
	posts_per_type = {}

	markdown_maker = html2text.HTML2Text()
	markdown_maker.body_width = 0
	markdown_maker.unicode_snob = 1
	markdown_maker.mark_code = 1

	while processed < total_posts:
		response = client.posts(host, limit=20, offset=processed, filter='raw')
		total_posts = response['total_posts']
		posts = response['posts']
		processed += len(posts)

		print "Processing..."
		for post in posts:
			print "	http://" + host + "/post/" + str(post["id"])

			try:
				posts_per_type[post['type']] += 1
			except KeyError:
				posts_per_type[post['type']] = 1

			postDate = datetime.strptime(post["date"], "%Y-%m-%d %H:%M:%S %Z")

			if post['type'] == 'text':
				title = post["title"]
				body = markdown_maker.handle(post["body"]) # Convert HTML body to Markdown
			# Ignore other post types for now
			else:
				break

			"""
			# Ignore other post types for now
			elif post["type"] == "photo":
				title = "Photo post"
				body = "{% img " + post["photos"][0]["original_size"]["url"] + " %}\n\n" + post["caption"]
			elif post["type"] == "video":
				title = "Video post"
				# Grab the widest embed code
				known_width = 0
				for player in post["player"]:
					if player["width"] > known_width:
						player_code = player["embed_code"]
				body = str(player_code) + "\n\n" + post["caption"]
			elif post["type"] == "link":
				title = "Link post"
				body = "<" + post["url"] + ">\n\n" + post["description"]
			elif post["type"] == "quote":
				title = "Quote post"
				body = post["source"] + "\n\n<blockquote>" + post["text"] + "</blockquote>"
			else:
				title = "(unknown post type)"
				body = "missing body"
				print post
			"""

			# Download images if requested
			if downloadImages:
				body = processPostBodyForImages(body, imagesPath, imagesUrlPath)

			# We have completely processed the post and the Markdown is ready to be output

			# Generate a slug out of the title: replace weird characters …
			slug = re.sub('[^0-9a-zA-Z- ]', '', title.lower().strip())

			# … collapse spaces …
			slug = re.sub(' +', ' ', slug)

			# … convert spaces to tabs …
			slug = slug.replace(' ', '-')

			# … and prepend date
			slug = postDate.strftime("%Y-%m-%d-") + slug

			# If path does not exist, make it
			if not os.path.exists(postsPath):
				os.makedirs(postsPath)

			f = codecs.open(findFileName(postsPath, slug), encoding='utf-8', mode="w")

			tags = ""
			if len(post["tags"]):
				tags = "[" + '"{0}"'.format('", "'.join(post["tags"])) + "]"

			draft = "false"
			if drafts:
				draft = "true"

			f.write("+++\ndate = \"" + postDate.strftime('%Y-%m-%dT%H:%M:%S%z+00:00') + "\"\ndraft = " + draft + "\ntags = " + tags + "\ntitle = \"" + title.replace('"', '\\"') + "\"\n+++\n" + body)

			f.close()

		print "Processed", processed, "out of", total_posts, "posts"

	print "Only text posts were converted into Hugo Markdown, the other types are skipped!"
	print "Posts per type:", posts_per_type

def findFileName(path, slug):
	"""Make sure the file doesn't already exist"""
	for attempt in range(0, 99):
		file_name = makeFileName(path, slug, attempt)
		if not os.path.exists(file_name):
			return file_name

	print "ERROR: Too many clashes trying to create filename " +  makeFileName(path, slug)
	exit()

def makeFileName(path, slug, exists = 0):
	suffix = "" if exists == 0 else "-" + str(exists + 1)
	return os.path.join(path, slug) + suffix + ".md"

def main():
	parser = argparse.ArgumentParser(description="Tumblr to Markdown downloader",
		epilog = """
		This app downloads all your Tumblr content into Markdown files that are suitable for processing with Octopress. Optionally also downloads the images hosted on Tumblr and replaces their URLs with locally hosted versions.
		""")
	parser.add_argument('--apikey', dest="apiKey", required=True, help="Tumblr API key")
	parser.add_argument('--host', dest="host", required=True, help="Tumblr site host, e.g example.tumblr.com")
	parser.add_argument('--posts-path', dest="postsPath", default="_posts", help="Output path for posts, by default “_posts”")
	parser.add_argument('--download-images', dest="downloadImages", action="store_true", help="Whether to download images hosted on Tumblr into a local folder, and replace their URLs in posts")
	parser.add_argument('--images-path', dest="imagesPath", default="images", help="If downloading images, store them to this local path, by default “images”")
	parser.add_argument('--images-url-path', dest="imagesUrlPath", default="/images", help="If downloading images, this is the URL path where they are stored at, by default “/images”")
	parser.add_argument('--drafts', dest="drafts", required=False, default=True, help="The created Hugo Markdown files will be set to draft=false by default. Set it to true if you want the posts to be in draft mode first.")

	args = parser.parse_args()

	if not args.apiKey:
		print "Tumblr API key is required."
		exit(0)

	if not args.host:
		print "Tumblr host name is required."
		exit(0)

	downloader(args.apiKey, args.host, args.postsPath, args.downloadImages, args.imagesPath, args.imagesUrlPath, args.drafts)

if __name__ == "__main__":
    main()
