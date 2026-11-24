import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { Feed } from "feed";
import { BLOG_DESCRIPTION, BLOG_TITLE, type Post } from "./blog-posts";

// Writes /blog/feed.xml, an RSS 2.0 feed of the published posts. Items carry
// the description, not the full text: posts link into the site by root-relative
// paths, which a feed reader would resolve against the wrong host.

export const FEED_PATH = "/blog/feed.xml";

export async function writeBlogFeed(outDir: string, siteUrl: string, posts: Post[]): Promise<void> {
  const feed = new Feed({
    id: `${siteUrl}/blog/`,
    title: BLOG_TITLE,
    description: BLOG_DESCRIPTION,
    link: `${siteUrl}/blog/`,
    language: "en",
    image: `${siteUrl}/og-image.png`,
    copyright: "bundlemcp",
    feedLinks: { rss: `${siteUrl}${FEED_PATH}` },
    updated: posts.length ? new Date(`${posts[0].date}T00:00:00Z`) : undefined,
  });
  for (const post of posts) {
    feed.addItem({
      title: post.title,
      link: `${siteUrl}${post.url}`,
      description: post.description,
      date: new Date(`${post.date}T00:00:00Z`),
      // RSS 2.0's <author> must be an e-mail address, so the name goes in dc:creator
      extensions: [{ name: "dc:creator", objects: { _text: post.author } }],
    });
  }
  // the library declares the dc namespace only for items with full content
  const xml = feed
    .rss2()
    .replace("<rss ", '<rss xmlns:dc="http://purl.org/dc/elements/1.1/" ');
  await writeFile(join(outDir, FEED_PATH), xml);
}
