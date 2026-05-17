import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
} from "@remix-run/react";

export default function App() {
  return (
    <html>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <link rel="preconnect" href="https://cdn.shopify.com/" />
        <link
          rel="stylesheet"
          href="https://cdn.shopify.com/static/fonts/inter/v4/styles.css"
        />
        {/*
          Inline favicon (data URL) — the customer-facing surface lives at
          thesigmavibe.shop/apps/vibe/* via App Proxy, and browsers
          default-request /favicon.ico against the *storefront* origin, not
          our Vercel deployment. Without a link tag the request 404s on
          Shopify and clutters the console. Inlining as a data URL skips
          any cross-origin asset plumbing and renders the Confident Luxe
          serif V (maroon on cream) in the browser tab.
        */}
        <link
          rel="icon"
          type="image/svg+xml"
          href="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%20100%20100'%3E%3Crect%20width='100'%20height='100'%20fill='%23faf5ee'/%3E%3Ctext%20x='50'%20y='72'%20font-size='72'%20text-anchor='middle'%20fill='%23b45a3c'%20font-family='Georgia,serif'%20font-style='italic'%3EV%3C/text%3E%3C/svg%3E"
        />
        <Meta />
        <Links />
      </head>
      <body>
        <Outlet />
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}
