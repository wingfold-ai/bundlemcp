import { postsLoader, type Post } from "../.vitepress/blog-posts";

// The posts for the blog index, newest first. The dev server lists drafts too,
// marked as drafts; `vitepress build` sets NODE_ENV to production, so the
// published index never does.
export declare const data: Post[];

export default postsLoader({ includeDrafts: process.env.NODE_ENV !== "production" });
