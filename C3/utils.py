import re
import csv
import json
import logging
import random
import torch

# import bert.tokenization as tokenization
import nezha.tokenization as tokenization
from torch.utils.data import TensorDataset, DataLoader, RandomSampler, SequentialSampler

n_class = 4
reverse_order = False
sa_step = False

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(name)s -   %(message)s',
                    datefmt='%m/%d/%Y %H:%M:%S',
                    level=logging.INFO)
logger = logging.getLogger(__name__)


class InputExample(object):
    """A single training/test example for simple sequence classification."""

    def __init__(self, guid, text_a, text_b=None, label=None, text_c=None):
        """Constructs a InputExample.

        Args:
            guid: Unique id for the example.
            text_a: string. The untokenized text of the first sequence. For single
            sequence tasks, only this sequence must be specified.
            text_b: (Optional) string. The untokenized text of the second sequence.
            Only must be specified for sequence pair tasks.
            label: (Optional) string. The label of the example. This should be
            specified for train and dev examples, but not for test examples.
        """
        self.guid = guid
        self.text_a = text_a
        self.text_b = text_b
        self.text_c = text_c
        self.label = label


class InputFeatures(object):
    """A single set of features of data."""

    def __init__(self, input_ids, input_mask, segment_ids, label_id):
        self.input_ids = input_ids
        self.input_mask = input_mask
        self.segment_ids = segment_ids
        self.label_id = label_id


class DataProcessor(object):
    """Base class for data converters for sequence classification data sets."""

    def get_train_examples(self):
        """Gets a collection of `InputExample`s for the train set."""
        raise NotImplementedError()

    def get_dev_examples(self):
        """Gets a collection of `InputExample`s for the dev set."""
        raise NotImplementedError()

    def get_labels(self):
        """Gets the list of labels for this data set."""
        raise NotImplementedError()

    @classmethod
    def _read_tsv(cls, input_file, quotechar=None):
        """Reads a tab separated value file."""
        with open(input_file, "r") as f:
            reader = csv.reader(f, delimiter="\t", quotechar=quotechar)
            lines = []
            for line in reader:
                lines.append(line)
            return lines


class MyProcessor(DataProcessor):
    def __init__(self, data_dir):
        random.seed(42)
        self.D = [[], [], []]

        for sid in range(3):
            data = []
            with open(data_dir + "split_" + ["train.json", "dev.json", "dev.json"][sid], "r",
                      encoding="utf8") as f:
                # with open(data_dir + "part_" + ["train.json", "dev.json", "dev.json"][sid], "r",
                #           encoding="utf8") as f:
                data += json.load(f)
            # for subtask in ["d", "m"]:
            #     with open("data/c3-" + subtask + "-" + ["train.json", "dev.json", "test.json"][sid], "r",
            #               encoding="utf8") as f:
            #         data += json.load(f)
            if sid == 0:
                random.shuffle(data)
            options = ["A", "B", "C", "D"]
            if sid == 3:
                pass
            else:
                for i in range(len(data)):
                    for ques in data[i]['Questions']:
                        each_data = [''.join(data[i]['Content']).lower(), ques['Question'].lower()]
                        for k in range(len(ques["Choices"])):
                            each_data += [ques["Choices"][k][2:].lower()]
                        for k in range(len(ques["Choices"]), 4):
                            each_data += ['']
                        each_data += [options.index(ques["Answer"])]
                        each_data += [ques["Q_id"]]
                        self.D[sid] += [each_data]

    def get_train_examples(self):
        """See base class."""
        return self._create_examples(
            self.D[0], "train")

    def get_dev_examples(self):
        """See base class."""
        return self._create_examples(
            self.D[1], "dev")

    def get_test_examples(self):
        """See base class."""
        return self._create_examples(
            self.D[2], "test")

    def get_labels(self):
        """See base class."""
        return ["0", "1", "2", "3"]

    @staticmethod
    def _create_examples(data, set_type):
        """Creates examples for the training and dev sets."""
        examples = []
        for (i, d) in enumerate(data):
            answer = str(data[i][6])  # Answer
            label = tokenization.convert_to_unicode(answer)

            for k in range(4):
                guid = "%s-%s-%s" % (set_type, i, k)
                text_a = tokenization.convert_to_unicode(data[i][0])
                text_b = tokenization.convert_to_unicode(data[i][k + 2])
                text_c = tokenization.convert_to_unicode(data[i][1])

                text_c = text_c.replace("（", "(").replace("）", ")")
                text_c = re.sub('[(*].*?[)]', '', text_c)

                examples.append(
                    InputExample(guid=guid, text_a=text_a, text_b=text_b, label=label, text_c=text_c))

        return examples


def convert_examples_to_features(examples, label_list, max_seq_length, tokenizer):
    """Loads a data file into a list of `InputBatch`s."""
    print("#examples", len(examples))
    label_map = {}
    for (i, label) in enumerate(label_list):
        label_map[label] = i

    features = [[]]

    for (ex_index, example) in enumerate(examples):
        content = tokenizer.tokenize(example.text_a)

        choice = tokenizer.tokenize(example.text_b)

        question = tokenizer.tokenize(example.text_c)

        _truncate_seq_tuple(content, choice, question, max_seq_length - 3)

        #         pair = question + ["[SEP]"] + choice
        pair = question + choice

        tokens = []
        segment_ids = []
        tokens.append("[CLS]")
        segment_ids.append(0)

        if pair:
            for token in pair:
                tokens.append(token)
                segment_ids.append(1)
            tokens.append("[SEP]")
            segment_ids.append(1)

        for token in content:
            tokens.append(token)
            segment_ids.append(0)
        tokens.append("[SEP]")
        segment_ids.append(0)

        input_ids = tokenizer.convert_tokens_to_ids(tokens)

        # The mask has 1 for real tokens and 0 for padding tokens. Only real
        # tokens are attended to.
        input_mask = [1] * len(input_ids)

        # Zero-pad up to the sequence length.
        while len(input_ids) < max_seq_length:
            input_ids.append(0)
            input_mask.append(0)
            segment_ids.append(0)

        assert len(input_ids) == max_seq_length
        assert len(input_mask) == max_seq_length
        assert len(segment_ids) == max_seq_length

        label_id = label_map[example.label]
        if ex_index % 1000 == 1:
            print("*** Example ***")
            print("guid: %s" % example.guid)
            print("tokens: %s" % " ".join(
                [tokenization.printable_text(x) for x in tokens]))
        #             print("label: %s (id = %d)" % (example.label, label_id))

        features[-1].append(
            InputFeatures(
                input_ids=input_ids,
                input_mask=input_mask,
                segment_ids=segment_ids,
                label_id=label_id))
        if len(features[-1]) == n_class:
            features.append([])

    if len(features[-1]) == 0:
        features = features[:-1]
    print('#features', len(features))

    return features


def get_dataloader(features, batch_size, is_train=False):
    input_ids = []
    input_mask = []
    segment_ids = []
    label_id = []

    for f in features:
        input_ids.append([])
        input_mask.append([])
        segment_ids.append([])
        label_id.append([])

        for each in f:
            input_ids[-1].append(each.input_ids)
            input_mask[-1].append(each.input_mask)
            segment_ids[-1].append(each.segment_ids)
        label_id[-1].append(f[0].label_id)

    all_input_ids = torch.tensor(input_ids, dtype=torch.long)
    all_input_mask = torch.tensor(input_mask, dtype=torch.long)
    all_segment_ids = torch.tensor(segment_ids, dtype=torch.long)
    all_label_ids = torch.tensor(label_id, dtype=torch.long)

    data = TensorDataset(all_input_ids, all_input_mask, all_segment_ids, all_label_ids)
    if is_train:
        sampler = RandomSampler(data)
    else:
        sampler = SequentialSampler(data)

    dataloader = DataLoader(data, sampler=sampler, batch_size=batch_size)

    return dataloader


def _truncate_seq_pair(tokens_a, tokens_b, max_length):
    """Truncates a sequence pair in place to the maximum length."""

    # This is a simple heuristic which will always truncate the longer sequence
    # one token at a time. This makes more sense than truncating an equal percent
    # of tokens from each, since if one sequence is very short then each token
    # that's truncated likely contains more information than a longer sequence.
    while True:
        total_length = len(tokens_a) + len(tokens_b)
        if total_length <= max_length:
            break
        if len(tokens_a) > len(tokens_b):
            tokens_a.pop()
        else:
            tokens_b.pop()


def _truncate_seq_tuple(tokens_a, tokens_b, tokens_c, max_length):
    """Truncates a sequence tuple in place to the maximum length."""

    # This is a simple heuristic which will always truncate the longer sequence
    # one token at a time. This makes more sense than truncating an equal percent
    # of tokens from each, since if one sequence is very short then each token
    # that's truncated likely contains more information than a longer sequence.
    while True:
        len_t_b = 0
        for t_b in tokens_b:
            len_t_b += len(t_b)
        # total_length = len(tokens_a) + len(tokens_b) + len(tokens_c)
        total_length = len(tokens_a) + len_t_b + len(tokens_c)
        if total_length <= max_length:
            break
        tokens_a.pop()

        # if len(tokens_a) >= len(tokens_b) and len(tokens_a) >= len(tokens_c):
        #     tokens_a.pop()
        # elif len(tokens_b) >= len(tokens_a) and len(tokens_b) >= len(tokens_c):
        #     tokens_b.pop()
        # else:
        #     tokens_c.pop()
