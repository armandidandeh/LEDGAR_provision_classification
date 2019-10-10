import numpy; numpy.random.seed(42)
import re
import pickle
from typing import List, Dict, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.linear_model import LogisticRegression
from utils import split_corpus, SplitDataSet, evaluate_multilabels, tune_clf_thresholds


def train_classifiers(x_train: numpy.array, y_train: numpy.array) -> OneVsRestClassifier:
    clf = LogisticRegression(class_weight='balanced', max_iter=10000, solver='lbfgs')
    ovr = OneVsRestClassifier(clf, n_jobs=-1)
    ovr.fit(x_train, y_train)
    return ovr


def stringify_labels(y_vecs: numpy.array, mlb: MultiLabelBinarizer,
                     thresh: float = 0.5, label_threshs: Dict[str, float] = None) -> List[List[str]]:
    """
    Turn prediction probabilities into label strings
    :param y_vecs:
    :param mlb:
    :param thresh:
    :param label_threshs: Classification threshold per label
    :return:
    """
    y_pred: List[List[str]] = []
    if not label_threshs:
        label_threshs = {l: thresh for l in mlb.classes_}
    label_threshs = [label_threshs[l] for l in mlb.classes_]
    for prediction in y_vecs:
        label_indexes = numpy.where(prediction >= label_threshs)[0]
        if label_indexes.size > 0:  # One of the classes has triggered
            labels = set(numpy.take(mlb.classes_, label_indexes))
        else:
            labels = []
        y_pred.append(labels)
    return y_pred


def classify_by_labelname(x_test: List[str], y_train: List[List[str]]) -> List[List[str]]:
    label_set = set(l for labels in y_train for l in labels)
    y_preds = []
    for i, x in enumerate(x_test):
        print(i, '\r', end='', flush=True)
        y_pred = []
        for label in label_set:
            if '_' in label:
                label = label.replace('_', ' ')
            if re.search(r'\b%s\b' % label, x.lower()) \
                    or (label.endswith('s') and re.search(r'\b%s\b' % label[:-1], x.lower())):
                y_pred.append(label)
        y_preds.append(y_pred)
    return y_preds


if __name__ == '__main__':

    predict_with_labelnames = False
    do_train = False
    do_test = False
    test_nda = True

    # corpus_file = '../sec_corpus_2016-2019_clean_projected_real_roots.jsonl'
    # classifier_file = 'saved_models/logreg_sec_clf_roots.pkl'

    corpus_file = 'data/sec_corpus_2016-2019_clean_NDA_PTs2.jsonl'
    classifier_file = 'saved_models/logreg_sec_clf_nda.pkl'

    # corpus_file = '../sec_corpus_2016-2019_clean_proto.jsonl'
    # classifier_file = 'saved_models/logreg_sec_clf_proto.pkl'

    # corpus_file = '../sec_corpus_2016-2019_clean_freq100.jsonl'
    # classifier_file = 'saved_models/logreg_sec_clf_freq100.pkl'

    print('Loading corpus from', corpus_file)
    dataset: SplitDataSet = split_corpus(corpus_file)
    print(len(dataset.y_train), 'training samples')
    print(len(dataset.y_test), 'test samples')
    print(len(dataset.y_dev), 'dev samples')
    label_set = set(l for labels in dataset.y_train for l in labels)
    print('Label set size:', len(label_set))

    if predict_with_labelnames:
        print('Predicting with label names')
        y_preds_labelnames = classify_by_labelname(dataset.x_test, dataset.y_train)
        evaluate_multilabels(dataset.y_test, y_preds_labelnames, do_print=True)

    print('Vectorizing')
    tfidfizer = TfidfVectorizer(sublinear_tf=True)
    x_train_vecs = tfidfizer.fit_transform(dataset.x_train)
    x_test_vecs = tfidfizer.transform(dataset.x_test)
    x_dev_vecs = tfidfizer.transform(dataset.x_dev)

    mlb = MultiLabelBinarizer().fit(dataset.y_train)
    y_train_vecs = mlb.transform(dataset.y_train)
    y_test_vecs = mlb.transform(dataset.y_test)

    if do_train:
        print('Training LogReg')
        classifier = train_classifiers(x_train_vecs, y_train_vecs)
        with open(classifier_file, 'wb') as f:
            pickle.dump(classifier, f)
    else:
        print('Loading classifier')
        with open(classifier_file, 'rb') as f:
            classifier = pickle.load(f)

    if do_test:
        y_preds_lr_probs_dev = classifier.predict_proba(x_dev_vecs)
        label_threshs = tune_clf_thresholds(y_preds_lr_probs_dev, dataset.y_dev, mlb)
        y_preds_lr_probs = classifier.predict_proba(x_test_vecs)
        y_preds_lr = stringify_labels(y_preds_lr_probs, mlb, label_threshs=label_threshs)
        # y_preds_lr_no_tresh = stringify_labels(y_preds_lr_probs, mlb)
        # print('LogReg results without classifier threshold tuning')
        # evaluate_multilabels(dataset.y_test, y_preds_lr_no_tresh, do_print=True)
        print('LogReg results with classifier threshold tuning')
        evaluate_multilabels(dataset.y_test, y_preds_lr, do_print=True)

    if test_nda:
        nda_file = 'data/nda_proprietary_data2_sampled.jsonl'
        print('Loading corpus from', nda_file)
        dataset_nda: SplitDataSet = split_corpus(nda_file)

        nda_x_train_vecs = tfidfizer.transform(dataset_nda.x_train)
        nda_x_test_vecs = tfidfizer.transform(dataset_nda.x_test)
        nda_x_dev_vecs = tfidfizer.transform(dataset_nda.x_dev)
        nda_y_train = mlb.transform(dataset_nda.y_train)
        nda_y_test = mlb.transform(dataset_nda.y_test)
        nda_y_dev = mlb.transform(dataset_nda.y_dev)

        # Zero-shot; no training on prop data
        print('Zero-shot: train on LEDGAR, predict proprietary')
        y_preds_nda_probs_dev = classifier.predict_proba(nda_x_dev_vecs)
        label_threshs_nda = tune_clf_thresholds(y_preds_nda_probs_dev, dataset_nda.y_dev, mlb)
        y_preds_nda_probs = classifier.predict_proba(nda_x_test_vecs)
        y_preds_nda = stringify_labels(y_preds_nda_probs, mlb, label_threshs=label_threshs_nda)
        evaluate_multilabels(dataset_nda.y_test, y_preds_nda, do_print=True)

        print('In-domain: train on proprietary, predict proprietary')
        tfidfizer_prop = TfidfVectorizer(sublinear_tf=True)
        x_train_prop_vecs = tfidfizer_prop.fit_transform(dataset_nda.x_train)
        x_test_prop_vecs = tfidfizer_prop.transform(dataset_nda.x_test)
        x_dev_prop_vecs = tfidfizer_prop.transform(dataset_nda.x_dev)

        classifier_prop = train_classifiers(x_train_prop_vecs, nda_y_train)
        y_preds_prop_prob_dev = classifier_prop.predict_proba(x_dev_prop_vecs)
        label_threshs_prop = tune_clf_thresholds(y_preds_prop_prob_dev, dataset_nda.y_dev, mlb)
        y_preds_prop_prob_test = classifier_prop.predict_proba(x_test_prop_vecs)
        y_preds_prop = stringify_labels(y_preds_prop_prob_test, mlb, label_threshs=label_threshs_prop)
        evaluate_multilabels(dataset_nda.y_test, y_preds_prop, do_print=True)

        # Join proprietary data and LEDGAR data; use separate TF IDF # TODO really? Use TFIDF of prop data
        print('Mixed: train on LEDGAR and proprietary, predict proprietary')
        x_train = dataset.x_train + dataset_nda.x_train[:int(len(dataset_nda.x_train)/4)]

        tfidfizer_mixed = TfidfVectorizer(sublinear_tf=True)
        x_train_vecs = tfidfizer_mixed.fit_transform(x_train)
        x_dev_vecs = tfidfizer_mixed.transform(dataset_nda.x_dev)
        x_test_vecs = tfidfizer_mixed.transform(dataset_nda.x_test)

        y_train = dataset.y_train + dataset_nda.y_train[:int(len(dataset_nda.x_train)/4)]

        classifier_mixed = train_classifiers(x_train_vecs, mlb.transform(y_train))

        y_preds_nda_probs_dev_mixed = classifier_mixed.predict_proba(x_dev_vecs)
        label_threshs_nda_mixed = tune_clf_thresholds(y_preds_nda_probs_dev_mixed, dataset_nda.y_dev, mlb)

        y_preds_nda_probs_mixed = classifier_mixed.predict_proba(x_test_vecs)
        y_preds_nda_mixed = stringify_labels(y_preds_nda_probs_mixed, mlb, label_threshs=label_threshs_nda_mixed)
        evaluate_multilabels(dataset_nda.y_test, y_preds_nda_mixed, do_print=True)

        """
        # Use all data as test set
        nda_x = dataset_nda.x_train + dataset_nda.x_test + dataset_nda.x_dev
        nda_y = dataset_nda.y_train + dataset_nda.y_test + dataset_nda.y_dev
        nda_x_vecs = tfidfizer.transform(nda_x)
        nda_y_vecs = mlb.transform(nda_y)
        
        y_preds_nda_probs = classifier.predict_proba(nda_x_vecs)
        y_preds_nda = stringify_labels(y_preds_nda_probs, mlb, label_threshs=label_threshs)
        y_preds_nda_nothresh = stringify_labels(y_preds_nda_probs, mlb)
        
        print('LogReg results NDA without classifier threshold tuning')
        evaluate_multilabels(nda_y, y_preds_nda_nothresh, do_print=True)
        print('LogReg results NDA with classifier threshold tuning')
        evaluate_multilabels(nda_y, y_preds_nda, do_print=True)
        """
