import csv
import json
from typing import Dict, List

import requests
import vcr

from fdr_cc_references import FDRCC_TO_CC_ACCOUNT_UUID

RESPONSE_BODY_TO_SKIP = [
    '{"error":"Couldn\'t perform \'get-chronicle-memos_account\' action: Failed!"}',
    '{"error":"Couldn\'t perform \'update_credit_bureau_score\' action: Cannot update credit score because of invalid credit date"}',
    '{"error":"Couldn\'t perform \'get_pending_and_declined_transactions\' action: Failure on [Filtered]: Error when connecting to First Data REST API"}',
    '{"error":"Couldn\'t perform \'get_cycle_posted_transactions\' action: Failure on [Filtered]: Error when connecting to First Data REST API"}',
    '{"error":"Couldn\'t perform \'get_statement_history\' action: Failure on [Filtered]: Error when connecting to First Data REST API"}',
    '{"error":"Couldn\'t perform \'create_account\' action: Failure on account creation: Error when connecting to First Data REST API"}',
]


class Sentry:
    """Query Sentry for events related to an issue"""

    ENDPOINT = "https://sentry.io/api/0/"

    def __init__(self):
        self.user_token = (
            ""
        )
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.user_token}"})

    @property
    def response_body_key(self):
        # return "response_body"
        return "fdr_response_body"

    # @vcr.use_cassette("fixtures/vcr_cassettes/issue/5912931583/events.yaml")
    def get_events_by_issue_id(self, issue_id: str):
        """Query for sentry events by issue ID

        Args:
            issue_id (str): A sentry issue ID

        Returns:
            requests.models.Response: response from Sentry
        """
        with vcr.use_cassette(  # save responses
            f"fixtures/vcr_cassettes/issue/{sentry_issue_id}/events.yaml",
            record_mode="new_episodes",
        ):
            response = self.session.get(
                "".join([self.ENDPOINT, "issues/", f"{issue_id}/", "events/"]),
                params={"full": "true"},
            )
        events = response.json()
        # events_we_care_about = []
        # for event in events:
        # if event["context"]["response_body"] in RESPONSE_BODY_TO_SKIP:
        #     continue

        # events_we_care_about.append(event)

        while response.links.get("next", {}).get("results", "false") == "true":
            next_url = response.links["next"].get("url")

            with vcr.use_cassette(  # save responses
                f"fixtures/vcr_cassettes/issue/{sentry_issue_id}/events.yaml",
                record_mode="new_episodes",
            ):
                response = self.session.get(next_url)

                events += response.json()
            # for event in events:
            # if event["context"]["response_body"] in RESPONSE_BODY_TO_SKIP:
            #     continue

            # events_we_care_about.append(event)

        for event in events:
            try:
                event["context"][self.response_body_key] = json.loads(
                    event["context"][self.response_body_key]
                )
            except json.JSONDecodeError:
                pass

        # from datetime import datetime
        # thing = datetime.fromisoformat(time)

        return events


class CSVWritter:
    def __init__(self, filename: str):
        self.filename = f"{filename}.csv"

    def write(self, entries: List[dict]):
        with open(self.filename, "w", encoding="utf8", newline="") as csv_file:
            fc = csv.DictWriter(
                csv_file,
                fieldnames=entries[0].keys(),
            )
            fc.writeheader()
            fc.writerows(entries)


def event_mapped_to_customer_error(events: List[dict]) -> Dict[str, Dict[str, dict]]:
    """Map Sentry events to cc api account UUID and error message

    Args:
        events (List[dict]): list of events for a Sentry issue

    Returns:
        Dict[str, Dict[str, dict]]: filtered dictionary of event data
            suitable for csv generation.
    """
    event_map: Dict[str, Dict[str, dict]] = {}

    for event in events:
        fdrcc_reference = event["context"]["fdrcc_reference"]
        error_message = event["context"]["response_body"]["message"]
        ccapi_account_uuid = FDRCC_TO_CC_ACCOUNT_UUID[fdrcc_reference]
        filtered_data = {
            "Sentry Event ID": event["id"],
            "ccapi_uuid": ccapi_account_uuid,
            "error_message": error_message,
            "time": event["dateReceived"],
        }

        if event_map.get(ccapi_account_uuid, {}).get(error_message):
            continue

        if customer := event_map.get(ccapi_account_uuid):
            customer[error_message] = filtered_data
        else:
            event_map[ccapi_account_uuid] = {error_message: filtered_data}

    return event_map


def events_to_fdrcc_reference(events: List[dict]) -> list:
    """Unique list of fdr cc references suitable for uses in querying in CC-API

    Args:
        events (List[dict]): events associated with a sentry issue

    Returns:
        list: fdrcc_references for all events
    """
    fdr_cc_references = [event["context"]["fdrcc_reference"] for event in events]

    return list(set(fdr_cc_references))


if __name__ == "__main__":
    sentry = Sentry()

    for name, sentry_issue_id in {
        "FDRActivateAccount": "4892094588"
        # "FDRGatewayServerError": "5942598678"
        # "ForceEmboss": "5912931583",
        # "NonReceipt": "5912931593",
    }.items():
        events = sentry.get_events_by_issue_id(sentry_issue_id)

    error_map: Dict[str, List[str]] = {}
    for event in events:
        if error := error_map.get(event["context"]["fdr_response_body"]):
            error.append(event["id"])
        else:
            error_map[event["context"]["fdr_response_body"]] = [event["id"]]

    for key in error_map.keys():
        print(key)
        # event_map = event_mapped_to_customer_error(events)

        # flattened_list = [
        #     error for errors in event_map.values() for error in errors.values()
        # ]

        # csv_writter = CSVWritter(name)
        # csv_writter.write(flattened_list)
