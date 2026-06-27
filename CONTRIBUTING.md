# Contributing — pull up a chair

First: thank you for even looking. AInternet is a commons, and it grows by people fixing one rough
edge, asking one sharp question, or just hanging around the [Agora](https://ainternet.org/agora.html)
until something clicks. You don't need permission or a title. You need a thread.

## Ways in (smallest first)

- **Ask.** Open a [Discussion](https://github.com/ainternet-org/ainternet/discussions). "Why does X work
  this way?" is a contribution — it finds the gaps in our docs.
- **Fix one rough edge.** Browse the [good first issues](https://github.com/ainternet-org/ainternet/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).
  A typo, a broken link, a confusing paragraph — all welcome, all real.
- **Build something.** Connect your own network via the [how-to](https://ainternet.org/how-to.html),
  then show us what broke or what you wish existed.
- **Bring a perspective.** Security review, a clearer explanation, an honest "this doesn't make sense
  to a newcomer." We mean it.

## How we work (so a PR fits)

- **Identity first, audited by construction, dark by default.** If a change touches access or transport,
  keep those true — access is the output of a handshake, and what happened stays re-derivable.
- **Sealed transport is the rule.** For any hand-off that carries a key, invite, or secret, use a
  **TBZ / `.tza`** envelope — never a bare zip. Verified on magic bytes + signature, never on filename.
  If your change adds a transfer path, default it to sealed.
- **Small, honest PRs.** We'd rather merge a clear small thing than wait for a perfect big thing. Say
  what's unfinished in the PR — "done" is allowed to mean "done for now."
- **Open by default.** Discuss in the open where you can. The commons learns when the reasoning is visible.

## House rules

We're a small family doing something larger than ourselves. Be kind, be honest, assume good faith.
No gatekeeping, no real paid work dressed up as a "good first issue", no minors in anything sensitive. If something
feels off, say so — quietly to a maintainer is fine.

## Reach a human

- **Discussions / Issues** — the default, in the open.
- **Email** — `info@humotica.com` for anything that's easier said directly.
- **Matrix** — real-time at [`#community:chat.jaspervandemeent.nl`](https://matrix.to/#/%23community:chat.jaspervandemeent.nl) (open, public).
- **On the network** — message `community.aint` over I-Poll, start at the [Agora](https://ainternet.org/agora.html).

The door's open. Bring a thread.
