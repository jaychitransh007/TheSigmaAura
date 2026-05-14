import type { ActionFunctionArgs } from "@remix-run/node";
import { authenticate } from "../shopify.server";
import db from "../db.server";

export const action = async ({ request }: ActionFunctionArgs) => {
    const { payload, session, topic, shop } = await authenticate.webhook(request);
    console.log(`Received ${topic} webhook for ${shop}`);

    const current = payload.current as string[];
    if (session) {
        await db.session.update({   
            where: {
                id: session.id
            },
            data: {
                // Shopify session storage expects space-separated scopes.
                // `Array.toString()` gives commas, which silently breaks
                // future session validation. Use explicit space join.
                scope: current.join(" "),
            },
        });
    }
    return new Response();
};
