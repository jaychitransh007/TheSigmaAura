do $$
begin
  if to_regclass('public.feedback_events') is null then
    return;
  end if;

  alter table public.feedback_events
    drop constraint if exists feedback_events_event_type_check;

  alter table public.feedback_events
    add constraint feedback_events_event_type_check
    check (event_type in ('dislike', 'like', 'share', 'buy', 'skip', 'no_action'));
end
$$;
