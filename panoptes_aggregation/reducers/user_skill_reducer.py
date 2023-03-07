'''
Subject Gold Standard Reducer for difficulty calculation
---------------------------------------------------------
This module provides functions to reduce the gold standard task extracts
to determine a `difficulty' score per subject (defined as the fraction
of succesful classification by all users for that subject)

See also: tess_gold_standard_reducer
'''
from .reducer_wrapper import reducer_wrapper
import numpy as np
from ..feedback_strategies import FEEDBACK_STRATEGIES
from sklearn.metrics import confusion_matrix


# smallest possible value for difficulty so that
# subjects have a non-negligible effect on user skill
# in extreme cases
DIFFICULTY_FLOOR = 0.05


@reducer_wrapper(relevant_reduction=True)
def user_skill_reducer(extracts, relevant_reduction=[], mode='binary', null_class='NONE',
                       skill_threshold=0.7, count_threshold=10, strategy='mean'):
    '''
        Parameters
        ----------
        extracts : list
            List of extracts
        relevant_reduction : list
            List of subject difficulty values attached as `relevant_reduction` on Caesar
        binary : boolean
            Flag for whether to use the binary (True/False for success) vs k-class method
            to calculate user skill [default: True]
        null_class : str
            Value for the NULL class for k-class method [default: 'NONE']
        skill_threshold : float
            Threshold for user skill to toggle the `level_up` flag [default: 0.7]
        count_threshold : int
            Threshold for the number of classifications done by the volunteer to get an accurate
            measurement of skill [default: 10]
        strategy : str
            Strategy to use to calculate the leveling up toggle:
             - `mean` : use the mean skill (excluding the NULL class) compared to the skill threshold
             - `all` : check every class against the threshold skill (all classes must be greater than the threshold)

        Returns
        -------
        data : dict
            A dictionary with the following keys:
                - classes : list
                    a list of classes (in the case of binary, this is [True, False])
                - confusion_simple : list
                    a confusion matrix using the raw counts (without subject difficulty weighting)
                - weighted_skill : dict
                    the subject difficulty weighted user skill per class
                - skill : dict
                    the simple (non-subject difficulty weighted) user skill per class
                - count : dict
                    the count of classifications per class
                - mean_skill : float
                    the average skill excluding the NULL class
                - level_up : bool
                    flag to show whether the user should be leveled up using the input thresholds
    '''
    if mode == 'binary':
        classes = ['True', 'False']
        confusion_simple, confusion_subject = get_confusion_matrix(extracts, relevant_reduction, mode, None)
    else:
        confusion_simple, confusion_subject, classes = \
            get_confusion_matrix(extracts, relevant_reduction, mode, null_class)

    # get both the weighted and non-weighted skill
    weight_per_class_skill = (confusion_subject.diagonal()) / (np.sum(confusion_subject, axis=1) + 1.e-16)
    per_class_skill = (confusion_simple.diagonal()) / (np.sum(confusion_simple, axis=1) + 1.e-16)

    weighted_per_class_skill_dict = {key: value for key, value in zip(classes, weight_per_class_skill)}
    per_class_skill_dict = {key: value for key, value in zip(classes, per_class_skill)}
    per_class_count = {key: value for key, value in zip(classes, np.sum(confusion_simple, axis=1))}

    # remove the null class from the skill array to calculate the mean skill
    if mode == 'binary':
        null_removed_classes = [classi for classi in classes if classi != 'False']
        null_removed_counts = [ci for classi, ci in per_class_count.items() if classi != 'False']
        mean_skill = np.sum([weighted_per_class_skill_dict[key] for key in null_removed_classes]) / (len(null_removed_classes) + 1.e-16)
    else:
        null_removed_classes = [classi for classi in classes if classi != null_class]
        null_removed_counts = [ci for classi, ci in per_class_count.items() if classi != null_class]
        mean_skill = np.sum([weighted_per_class_skill_dict[key] for key in null_removed_classes]) / (len(null_removed_classes) + 1.e-16)

    # check the leveling up value
    if strategy == 'mean':
        level_up = (mean_skill >= skill_threshold) & all([c >= count_threshold for c in null_removed_counts])
    elif strategy == 'all':
        level_up = all([weighted_per_class_skill_dict[s] >= skill_threshold for s in null_removed_classes]) & all([c >= count_threshold for c in null_removed_counts])

    return {'classes': classes,
            'confusion_simple': confusion_simple.tolist(),
            'weighted_skill': weighted_per_class_skill_dict,
            'skill': per_class_skill_dict,
            'count': per_class_count,
            'mean_skill': mean_skill,
            'level_up': level_up
            }


def get_confusion_matrix(extracts, relevant_reduction, mode, null_class):
    '''
        Returns two confusion matrices (both unweighted and weighted by subject difficulty),
        and the list of classes (for a k-class run). Note: confusion matrix for the k-class
        version is a pseudo-confusion matrix since there can be multiple true classes and multiple
        chosen classes per classification. This will require a many-to-many comparison which is
        inherently impossible. Therefore, we compare all incorrectly chosen classes with the "null"
        class instead.

        Parameters
        ----------
        extracts : list
            List of extracts for a given user
        relevant_reduction : dict
            Dictionary containing the `subject_difficulty` array that gives
            the difficulty of the all the subjects seen by the user
        mode : str
            Whether to run the reducer in binary (True/False) mode or k-class mode
        null_class : string
            The value of the null/non-existant class for the many-to-many k-class mode

        Returns
        -------
        confusion_simple : list
            Simple confusion matrix without subject difficulty weighting
        confusion_subject : list
            Confusion matrix with subject difficulty weighting
        classes : list
            List of unique classes corresponding to indices of the confusion matrix.
            Only returned for k-class mode
    '''
    if mode == 'binary':
        return get_user_skill_binary(extracts, relevant_reduction)
    else:
        strategy = extracts[0]['feedback']['strategy']

        user_classifications = []
        classes = []

        true_key = 'true_' + FEEDBACK_STRATEGIES[strategy][0]

        true_values = []

        # first we need a list of labels
        # obtain a list of labels from user classifications
        for extracti in extracts:
            user_classifications += [key for key in extracti.keys() if isinstance(extracti[key], int) & (extracti[key] == 1)]

            # convert all answers to lower case to be consistent across both lists
            classes += [key.lower() for key in extracti.keys() if isinstance(extracti[key], int)]
            true_values.extend(list(map(lambda e: e.lower(), extracti['feedback'][true_key])))

        # get a full list of classes as the union of the two sets of labels
        classes = np.sort(np.unique([*np.unique(classes), *np.unique(true_values)]))
        classes = classes.tolist()

        difficulties = []
        for reductioni in relevant_reduction:
            difficulties.append(np.mean(reductioni['data']['difficulty']))

        subject_difficulty = 1 - np.asarray(difficulties)

        # find the easiest subject in the set and set all fully successful
        # subjects to this "easy" score. limit the easy score to 0.05 so that
        # we don't have a runaway growth of easy weights
        difficulty_min = np.max([np.min(subject_difficulty[subject_difficulty > 0], initial=0), DIFFICULTY_FLOOR])

        # limit the difficulty to a mininum of 0.05 so that
        # easy subjects still have some weight
        subject_difficulty[subject_difficulty == 0] = difficulty_min

        # we will loop through all the extracts and create a list
        # of user classified label and a corresponding gold standard
        # label. then, the confusion matrix is just determined using
        # the element-wise comparison between the two lists
        if mode == 'one-to-one':
            true_counts, class_counts, subject_difficulties = get_one_to_one(extracts, subject_difficulty, true_key)
        elif mode == 'many-to-many':
            true_counts, class_counts, subject_difficulties = get_multi_class(extracts, subject_difficulty, true_key, null_class)
            classes.append(null_class)

        # get the simple confusion matrix without the subject difficulty
        confusion_simple = confusion_matrix(true_counts, class_counts, labels=classes)

        # get the more complicated confusion matrix accounting for subject difficulty
        confusion_subject = confusion_matrix(true_counts, class_counts, sample_weight=subject_difficulties,
                                             labels=classes)

        return (confusion_simple, confusion_subject, classes)


def get_user_skill_binary(extracts, relevant_reduction):
    # binary always defaults to 2x2 where the second column
    # (gold standard = False) is NaN
    confusion_simple = np.zeros((2, 2))
    confusion_subject = np.zeros((2, 2))

    successes = []
    difficulties = []

    # create an array of success/failure. multiple cases
    # per subject are treated independently, and the final
    # array is a flattened version of all success/failure checks
    for extracti, reductioni in zip(extracts, relevant_reduction):
        successes.extend(extracti['feedback']['success'])

        # input difficulty is inverted... we want higher difficulty
        # values for subjects which were classified incorrectly
        difficultyi = 1. - np.array(reductioni['data']['difficulty'])

        difficulties.extend(list(difficultyi))
    successes = np.asarray(successes)
    difficulties = np.asarray(difficulties)

    # find the easiest subject in the set and set all fully successful
    # subjects to this "easy" score. limit the easy score to 0.05 so that
    # we don't have a runaway growth of easy weights
    difficulty_min = np.max([np.min(difficulties[difficulties > 0], initial=0), DIFFICULTY_FLOOR])

    # limit the difficulty to a mininum of 0.05 so that
    # easy subjects still have some weight
    difficulties[difficulties == 0] = difficulty_min

    true_mask = successes == 1
    false_mask = successes == 0

    # create the confusion matrix from the list of success/failures
    confusion_simple[0, 0] = np.sum(true_mask)
    confusion_simple[1, 0] = np.sum(false_mask)
    confusion_simple[:, 1] = 0

    # the true score is the sum of difficulties of the correct classifications
    # so hard subjects give you a boost in score and the easy subjects
    # give you a small increase
    confusion_subject[0, 0] = np.sum(difficulties[true_mask])

    # do the opposite for failure scores: easy subject failures should be
    # penalized more strongly compared to difficulty failures
    neg_difficulty = 1. - difficulties[false_mask]
    neg_difficulty[neg_difficulty == 0] = difficulty_min
    confusion_subject[1, 0] = np.sum(neg_difficulty)
    confusion_subject[:, 1] = 0

    return (confusion_simple.T, confusion_subject.T)


def get_multi_class(extracts, subject_difficulty, true_key, null_class):
    true_counts = []
    class_counts = []
    subject_difficulties = []

    for j, extract in enumerate(extracts):
        # find a list of user classified labels in this extract
        user_class_i = [key.lower() for key in extract.keys() if isinstance(extract[key], int) & (extract[key] == 1)]
        true_keys = [key.lower() for key in extract['feedback'][true_key]]

        # get a full list of classifications
        classi = np.sort(np.unique([*np.unique(true_keys),
                                    *np.unique(user_class_i)]))
        classi = classi.tolist()

        # create a temporary list of classes that will
        # incorporate both the user selected classes
        # and the tru classes
        true_count_i = [null_class] * len(classi)

        # loop through the true classes and populate the corresponding
        # indices in the list
        for value in true_keys:
            true_count_i[classi.index(value)] = value

        # do the same for the user classifications
        class_count_i = [null_class] * len(classi)

        for value in user_class_i:
            class_count_i[classi.index(value)] = value

        # add both lists to the master list of
        # classifications and true classes
        true_counts.extend(true_count_i)
        class_counts.extend(class_count_i)

        # also add the subject difficulties for each extract. subject
        # difficulty per class is not trivial to do, so we will average
        # the subject difficulty across all the classes in this subject.
        # easy subjects should get small bump for correct classifications
        # while difficult subjects will get a huge bump for success
        # do the opposite for failure scores: easy subject failures should be
        # penalized more strongly compared to difficulty failures
        subject_difficulty_i = [subject_difficulty[j]] * len(classi)
        for class_ind in range(len(classi)):
            if true_count_i[class_ind] != class_count_i[class_ind]:
                subject_difficulty_i[class_ind] = max([1. - subject_difficulty[j], DIFFICULTY_FLOOR])

        subject_difficulties.extend(subject_difficulty_i)

    return true_counts, class_counts, subject_difficulties


def get_one_to_one(extracts, subject_difficulty, true_key):
    true_counts = []
    class_counts = []
    subject_difficulties = []

    for j, extract in enumerate(extracts):
        # find a list of user classified labels in this extract
        # here, we know that there is only one classification class and true class
        user_class_i = [key.lower() for key in extract.keys() if isinstance(extract[key], int) & (extract[key] == 1)]
        true_keys = [key.lower() for key in extract['feedback'][true_key]]

        # also add the subject difficulties for each extract. subject
        # difficulty per class is not trivial to do, so we will average
        # the subject difficulty across all the classes in this subject.
        # easy subjects should get small bump for correct classifications
        # while difficult subjects will get a huge bump for success
        # do the opposite for failure scores: easy subject failures should be
        # penalized more strongly compared to difficulty failures
        if user_class_i == true_keys:
            subject_difficulties.append(max([subject_difficulty[j], DIFFICULTY_FLOOR]))
        else:
            subject_difficulties.append(max([1 - subject_difficulty[j], DIFFICULTY_FLOOR]))

        true_counts.extend(true_keys)
        class_counts.extend(user_class_i)

    return true_counts, class_counts, subject_difficulties
