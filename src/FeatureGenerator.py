from nltk.corpus import stopwords
from nltk.tokenize import RegexpTokenizer
from nltk.metrics.distance import edit_distance
from nltk.stem.snowball import SnowballStemmer
from nltk.stem.wordnet import WordNetLemmatizer

from scigraph.kb.kb_utils_refactor import KnowledgeBase
import scigraph.ontology_matching.string_utils as string_utils
import scigraph.ontology_matching.constants as constants


# class for generating features between entities of two KBs
class FeatureGenerator:
    def __init__(self, s_kb: KnowledgeBase, t_kb: KnowledgeBase):
        self.SYNONYM_REL_LABELS = ['RL', 'RQ', 'RU', 'SY']
        self.PARENT_REL_LABELS = ['RB', 'PAR', 'Is a', 'Part of', 'subClassOf', 'is_a', 'part_of']
        self.CHILD_REL_LABELS = ['RN', 'CHD', 'Has part', 'subClass', 'has_part']
        self.SIBLING_REL_LABELS = ['SIB', 'RO']

        self.s_kb = s_kb
        self.t_kb = t_kb

        self.STOP = set(stopwords.words('english'))
        self.tokenizer = RegexpTokenizer(r'[A-Za-z\d]+')
        self.stemmer = SnowballStemmer("english")
        self.lemmatizer = WordNetLemmatizer()

        self.s_tokens = dict()
        self.t_tokens = dict()

        self._generate_token_maps()

    def _get_ent_names_from_relations(self, ent, kb, rel_types):
        """
        fetch the set of entity names that are related to the given entity
        :param ent:
        :param kb:
        :param rel_types: set of relations to extract
        :return:
        """
        matching_rels = [kb.relations[rel_id] for rel_id in ent.relation_ids]

        ent_ids = [
            rel.entity_ids[1] for rel in matching_rels
            if rel.relation_type in rel_types and
            rel.entity_ids[1] in kb.research_entity_id_to_entity_index
        ]

        ent_names = []
        for ent_id in ent_ids:
            ent = kb.get_entity_by_research_entity_id(ent_id)
            if ent:
                ent_names.append(tuple(string_utils.tokenize_string(string_utils.normalize_string(
                    ent.canonical_name), self.tokenizer, self.STOP))
                )

        return ent_names

    def _compute_tokens(self, ent, kb):
        """
        Compute tokens from given entity in kb
        :param ent:
        :param kb:
        :return:
        """
        name_string = string_utils.normalize_string(ent.canonical_name)
        name_tokens = string_utils.tokenize_string(name_string, self.tokenizer, self.STOP)
        stemmed_tokens = tuple([self.stemmer.stem(w) for w in name_tokens])
        lemmatized_tokens = tuple([self.lemmatizer.lemmatize(w) for w in name_tokens])
        character_tokens = tuple(string_utils.get_character_n_grams(
            name_string, constants.NGRAM_SIZE
        ))

        alias_tokens = []

        for a in ent.aliases:
            alias_tokens.append(string_utils.tokenize_string(
                string_utils.normalize_string(a), self.tokenizer, self.STOP))

        parent_names = self._get_ent_names_from_relations(
            ent, kb, self.PARENT_REL_LABELS
        )

        child_names = self._get_ent_names_from_relations(
            ent, kb, self.CHILD_REL_LABELS
        )
        return [
            name_tokens, stemmed_tokens, lemmatized_tokens, character_tokens,
            alias_tokens,
            set(parent_names),
            set(child_names)
        ]

    def _generate_token_maps(self):
        """
        Generate token maps between two KBs
        :return:
        """

        for s_ent in self.s_kb.entities:
            self.s_tokens[s_ent.research_entity_id] = self._compute_tokens(
                s_ent, self.s_kb
            )

        for t_ent in self.t_kb.entities:
            self.t_tokens[t_ent.research_entity_id] = self._compute_tokens(
                t_ent, self.t_kb
            )

        return

    def calculate_features(self, s_ent_id, t_ent_id):
        """
        Calculate features between two entities s_ent and t_ent from source and target KBs respectively
        :param s_ent_id: entity id from source KB
        :param t_ent_id: entity id from target KB
        :return:
        """
        s_name_tokens, s_stemmed_tokens, s_lemmatized_tokens, s_char_tokens, \
        s_alias_tokens, s_parent_names, s_child_names = self.s_tokens[
            s_ent_id
        ]
        t_name_tokens, t_stemmed_tokens, t_lemmatized_tokens, t_char_tokens, \
        t_alias_tokens, t_parent_names, t_child_names = self.t_tokens[
            t_ent_id
        ]

        features = dict()

        # boolean features
        features['has_same_canonical_name'] = (s_name_tokens == t_name_tokens)
        features['has_same_stemmed_name'] = (s_stemmed_tokens == t_stemmed_tokens)
        features['has_same_lemmatized_name'] = (s_lemmatized_tokens == t_lemmatized_tokens)
        features['has_same_char_tokens'] = (s_char_tokens == t_char_tokens)
        features['has_alias_in_common'] = (
            len(set(s_alias_tokens).intersection(set(t_alias_tokens))) > 0
        )

        # jaccard similarity and token edit distance
        max_changes = len(s_name_tokens) + len(t_name_tokens)
        max_char_changes = len(s_char_tokens) + len(t_char_tokens)

        if features['has_same_canonical_name']:
            features['name_token_jaccard'] = 1.0
            features['inverse_name_edit_distance'] = 1.0
        else:
            features['name_token_jaccard'] = string_utils.get_jaccard_similarity(
                set(s_name_tokens), set(t_name_tokens)
            )
            features['inverse_name_edit_distance'] = 1.0 - edit_distance(
                s_name_tokens, t_name_tokens
            ) / max_changes

        if features['has_same_stemmed_name']:
            features['stemmed_token_jaccard'] = 1.0
            features['inverse_stemmed_edit_distance'] = 1.0
        else:
            features['stemmed_token_jaccard'] = string_utils.get_jaccard_similarity(
                set(s_stemmed_tokens), set(t_stemmed_tokens)
            )
            features['inverse_stemmed_edit_distance'] = 1.0 - edit_distance(
                s_stemmed_tokens, t_stemmed_tokens
            ) / max_changes

        if features['has_same_lemmatized_name']:
            features['lemmatized_token_jaccard'] = 1.0
            features['inverse_lemmatized_edit_distance'] = 1.0
        else:
            features['lemmatized_token_jaccard'] = string_utils.get_jaccard_similarity(
                set(s_lemmatized_tokens), set(t_lemmatized_tokens)
            )
            features['inverse_lemmatized_edit_distance'] = 1.0 - edit_distance(
                s_lemmatized_tokens, t_lemmatized_tokens
            ) / max_changes

        if features['has_same_char_tokens']:
            features['char_token_jaccard'] = 1.0
            features['inverse_char_token_edit_distance'] = 1.0
        else:
            features['char_token_jaccard'] = string_utils.get_jaccard_similarity(
                set(s_char_tokens), set(t_char_tokens)
            )
            features['inverse_char_token_edit_distance'] = 1 - edit_distance(
                s_char_tokens, t_char_tokens
            ) / max_char_changes

        max_alias_token_jaccard = 0.0
        min_alias_edit_distance = 1.0

        if not features['has_alias_in_common']:
            for s_a_tokens in s_alias_tokens:
                for t_a_tokens in t_alias_tokens:
                    if s_a_tokens and t_a_tokens:
                        j_ind = string_utils.get_jaccard_similarity(
                            set(s_a_tokens), set(t_a_tokens)
                        )
                        if j_ind > max_alias_token_jaccard:
                            max_alias_token_jaccard = j_ind
                        e_dist = edit_distance(s_a_tokens, t_a_tokens) / (
                            len(s_a_tokens) + len(t_a_tokens)
                        )
                        if e_dist < min_alias_edit_distance:
                            min_alias_edit_distance = e_dist

        features['max_alias_token_jaccard'] = max_alias_token_jaccard
        features['inverse_min_alias_edit_distance'] = 1.0 - min_alias_edit_distance

        # has any relationships
        has_parents = (len(s_parent_names) > 0 and len(t_parent_names) > 0)
        has_children = (len(s_child_names) > 0 and len(t_child_names) > 0)

        percent_parents_in_common = 0.0
        percent_children_in_common = 0.0

        # any relationships in common
        if has_parents:
            max_parents_in_common = (len(s_parent_names) + len(t_parent_names)) / 2
            percent_parents_in_common = len(
                s_parent_names.intersection(t_parent_names)
            ) / max_parents_in_common

        if has_children:
            max_children_in_common = (len(s_child_names) + len(t_child_names)) / 2
            percent_children_in_common = len(
                s_child_names.intersection(t_child_names)
            ) / max_children_in_common

        features['percent_parents_in_common'] = percent_parents_in_common
        features['percent_children_in_common'] = percent_children_in_common

        return features
