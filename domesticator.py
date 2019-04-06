#!/home/rdkibler/.conda/envs/domesticator/bin/python



##also look into pytest




print("Note: stop supporting DNA sequence inputs and multiple domestication sites")

#New features I want:
#	only optimize coding sequences
#	optimize against hairpins globally (even between coding and non-coding sequences)


#What I want this to do is take a protein sequence and convert it into an orderable gblock
#to do this, it'll need 
#	1. the protein sequence, 
#	2. the cloning scheme being used (MoClo-YTK, EMMA, BioBricks, etc)
#	3. specific identification required by the clonging scheme (ie MoClo-YTK type) 
#	Optional override to cloning scheme and identifiaction if you just specify the left and right flanking sequences 
#	4. the destination organism (to optimize codon usage), 
#	5. a list of sequences to avoid (like restriction sites) (default to avoid the type-II restriction sites or whatever sites used by whatever standards)
#	6. the name of the sequence (has a default value)
#	6. a flag specifiying output to be in the form of a fasta file (in which case you must also specifiy the file name), gb file, or fasta print to terminal
#		if you write to gb file, then it'll include the cloning system you specify, the part type (or whatever), and specify wether or not the overhangs are custom


#default behavior will be to codon optimize a cds
#I plan on optimizing I definitely want to be able to optimize a sequence for synthesis/GC content while preserving patterns, however, I will not be implementing that right away

import sys

database='/home/rdkibler/projects/domesticator/database/'
sys.path.insert(0, database)

#import json
from collections import Counter
#from dnachisel import *
from dnachisel import EnforceTranslation, AvoidChanges, DnaOptimizationProblem, CodonOptimize, AvoidPattern, HomopolymerPattern, EnzymeSitePattern, EnforceGCContent, EnforceTerminalGCContent, AvoidHairpins
from dnachisel import Location
from dnachisel import reverse_translate
import argparse
import warnings
from Bio import SeqIO
#from Bio.SeqFeature import *
from Bio.Seq import MutableSeq, Seq
from Bio.SeqRecord import SeqRecord
from Bio.SeqFeature import FeatureLocation
from Bio.Alphabet import IUPAC
#from Bio.PDB import PDBParser, PPBuilder
from constraints import ConstrainCAI
from objectives import MinimizeSecondaryStructure
import os



def load_template(filename, insert, destination):
	''' func descriptor '''

	objectives = []
	constraints = []

	vector = SeqIO.read(filename, "genbank")
	

	vector, insert_location = insert_into_vector(vector, destination, insert)

	problem = DnaOptimizationProblem.from_record(vector)
	constraints += problem.constraints
	objectives += problem.objectives

	#feats = [feat.qualifiers for feat in vector.features]
	#dnachisel hasn't implemented MultiLocation yet
	#vector_location = FeatureLocation(insert_location.end, len(vector)) + FeatureLocation(0,insert_location.start)
	#vector_location_us = Location(0, insert_location.start, 1)
	#vector_location_ds = Location(insert_location.end, len(vector), 1)

	#constraints.append(EnforceTranslation(Location.from_biopython_location(insert_location)))
	#constraints.append(AvoidChanges(vector_location_us))
	#constraints.append(AvoidChanges(vector_location_ds))



	

	#This seq should be a SeqRecord object
	return vector, objectives, constraints



def replace_sequence_in_record(record, location, new_seq):
	#print(record, location, new_seq)
	#print(dir(location))
	#print(location.extract(record.seq))
	#print(record.seq[location.start:location.end])
	
	if location.strand >= 0:
		adjusted_seq = record.seq[:location.start] + new_seq.seq + record.seq[location.end:]
	else:
		adjusted_seq = record.seq[:location.start] + new_seq.reverse_complement().seq + record.seq[location.end:]

	#exit(adjusted_seq)
	record.seq = adjusted_seq

	#print(help(location))
	#exit(dir(location))

	seq_diff = len(new_seq) - len(location)
	orig_start = location.start
	orig_end = location.end

	processed_features = []

	#print("-=-=-=-=-=-=-=-=-=-==---=-=-=-=-=-=")
	#print(location)
	#print("diff: %d" % seq_diff)

	#adjust all features
	for feat in record.features:
		#print("----------------------------------------")
		#print(feat.qualifiers['label'][0])
		#print(feat.location)

		f_loc = feat.location

		loc_list = []

		for subloc in f_loc.parts:

			assert(subloc.start <= subloc.end)
			
			#type 1: where the start and end are contained within the original location
			#-> do not add it to the processed_features list
			if subloc.start > location.start and subloc.start < location.end and subloc.end > location.start and subloc.end < location.end:
				#print("start: %d and end: %d are contained within %s" % (subloc.start, subloc.end, location))
				#print("omit")
				continue

			#type 1b: where the start and end are the same which will happen a lot for storing constraints and objectives
			elif subloc.start == location.start and subloc.end == location.end:
				new_loc = FeatureLocation(location.start, location.end + seq_diff, strand=subloc.strand)



			#type 2: where they start or end inside the location
			#-> chop off. don't forget to add on approprate amount
			##THINK! does strand even matter? How is start and end defined? I'm assuming that for strand -1 things are flipped but that's probably not how it's implemented. Also, consider strand = 0 (no direction). There is probably an easier way. 
			elif subloc.start >= location.start and subloc.start <= location.end:
				#print("start: %d is in %s" % (subloc.start, location))
				new_loc = FeatureLocation(location.end + seq_diff, subloc.end + seq_diff, strand=subloc.strand)

			elif subloc.end >= location.start and subloc.end <= location.end:
				#print("end: %d is in %s" % (subloc.end, location))
				new_loc = FeatureLocation(subloc.start, location.start, strand=subloc.strand)
				

			#type 3: where they span the location 
			#-> keep the leftmost point same and add diff to rightmost. do not split
			elif location.start >= subloc.start and location.start <= subloc.end and location.end >= subloc.start and location.end <= subloc.end:
				#print("loc spans insert. keep start and add diff to end")
				new_loc = FeatureLocation(subloc.start, subloc.end + seq_diff, strand=subloc.strand)

			#type 4: where they start and end before location
			#-> add it to list unchanged
			elif subloc.start <= location.start and subloc.end <= location.start:
				#print("loc is before insert location so just keep")
				new_loc = subloc

			#type 5: where they start and end after location
			#-> add diff to whole location
			elif subloc.start >= location.end and subloc.end >= location.end:
				#print("loc is after insert location so apply offset and keep")
				new_loc = subloc + seq_diff

			loc_list.append(new_loc)
			#print("new loc:")
			#print(new_loc)
		
		#if the list is empty, it means that all the sublocs were contained within the insert
		if loc_list:
			feat.location = sum(loc_list)
			processed_features.append(feat)


	record.features = processed_features


	return record

def load_user_options(args, location):
	#set enforce translation to the whole thing
	constraints = []
	objectives = []

	if args.harmonized:
		opt_mode = 'harmonized'
	else:
		opt_mode = 'best_codon'
	objectives += [
		CodonOptimize(species=args.species, location=location, mode=opt_mode), 
		EnforceTranslation(location=location)]

	if args.avoid_homopolymers:
		constraints += [
		AvoidPattern(HomopolymerPattern("A",args.avoid_homopolymers),location=location),
		AvoidPattern(HomopolymerPattern("T",args.avoid_homopolymers),location=location),
		AvoidPattern(HomopolymerPattern("G",args.avoid_homopolymers),location=location),
		AvoidPattern(HomopolymerPattern("C",args.avoid_homopolymers),location=location)]

	if args.avoid_hairpins:
		constraints += [AvoidHairpins(location=location)]

	if args.avoid_patterns:
		constraints += [AvoidPattern(pattern,location=location) for pattern in args.avoid_patterns]

	if args.avoid_restriction_sites:
		constraints += [AvoidPattern(EnzymeSitePattern(enzy),location=location) for enzy in args.avoid_restriction_sites]

	if args.constrain_global_GC_content:
		constraints += [EnforceGCContent(mini=args.global_GC_content_min, maxi=args.global_GC_content_max, location=location)]

	if args.constrain_local_GC_content:
		constraints += [EnforceGCContent(mini=args.local_GC_content_min, maxi=args.global_GC_content_max, window=args.local_GC_content_window, location=location)]

	if args.constrain_terminal_GC_content:
		constraints += [EnforceTerminalGCContent(mini=args.terminal_GC_content_min, maxi=args.terminal_GC_content_max, window_size=8, location=location)]

	if args.constrain_CAI:
		constraints += [ConstrainCAI(species=args.species, minimum=args.constrain_CAI_minimum, location=location)]

	if args.optimize_dicodon_frequency:
		objectives += [MaximizeDicodonAdaptiveIndex()]

	if args.avoid_secondary_structure:
		objectives += [MinimizeSecondaryStructure(max_energy=args.avoid_secondary_structure_max_e, location=location, boost=args.avoid_secondary_structure_boost)]

	if args.avoid_initiator_secondary_structure:
		objectives += [MinimizeSecondaryStructure(max_energy=args.avoid_initiator_secondary_structure_max_e, location=location, optimize_initiator=True, boost=args.avoid_initiator_secondary_structure_boost)]

	return objectives, constraints

def find_annotation(record, label):
	for feat in record.features:
		if label == feat.qualifiers['label'][0]:
			#I will be replacing it so remove it:
			#vector.features.remove(feat)
			return feat
	exit("label not found: " + label)

def insert_into_vector(vector, destination, new_seq):
	
	destination_annotation = find_annotation(vector, destination)
	#print(destination_annotation)

	location = destination_annotation.location

	#print(vector)
	#print(vector.features)
	#print(dir(vector.features))
	vector = replace_sequence_in_record(vector, location, new_seq)

	#re-annotate the thing
	insert_loc = FeatureLocation(location.start, location.start + len(new_seq), strand=location.strand)
	destination_annotation.location = insert_loc
	destination_annotation.qualifiers['label'][0] = new_seq.name
	vector.features.append(destination_annotation)

	return vector, insert_loc

def load_inserts(inputs):
	rec_counter = 1
	inserts = []
	chain="ABCDEFGHIJKLMNOPQRSTUVWXYZ"

	for this_input in inputs: 
		if os.path.isfile(this_input):
			ext = os.path.splitext(this_input)[1]
			if ext == 'fasta':
				for record in SeqIO.parse(input_filename, 'fasta'):
					record.seq = Seq(reverse_translate(record.seq), IUPAC.unambiguous_dna)
					inserts.append(record)
			elif exit == 'pdb':
				for chain_num, record in enumerate(SeqIO.parse(input_pdb, "pdb-atom")):
					name = os.path.splitext(os.path.basename(input_pdb))[0] + "_" + chain[chain_num]
					record.seq = Seq(reverse_translate(record.seq), IUPAC.unambiguous_dna)
					record.id=name
					record.name=name
					inserts.append(record)
			else:
				exit("extension not recognized: " + ext)
		else:
			record = SeqRecord(Seq(reverse_translate(input_sequence),IUPAC.unambiguous_dna), id="unknown_seq%d" % rec_counter, name="unknown_seq%d" % rec_counter, description="domesticator-optimized DNA sequence")
			rec_counter += 1
			inserts.append(record)


	# if mode == "protein_fasta_file":
	# 	for input_filename in inputs:
	# 		for record in SeqIO.parse(input_filename, 'fasta'):
	# 			record.seq = Seq(reverse_translate(record.seq), IUPAC.unambiguous_dna)
	# 			inserts.append(record)
	# # elif mode == "DNA_fasta_file":
	# 	for input_filename in inputs:
	# 		for record in SeqIO.parse(input_filename, 'fasta'):
	# 			assert(len(record.seq) % 3 == 0)
	# 			record.seq = Seq(str(record.seq), IUPAC.unambiguous_dna)
	# 			inserts.append(record)
	# elif mode == "protein_sequence":
	# 	for input_sequence in inputs:
	# 		record = SeqRecord(Seq(reverse_translate(input_sequence),IUPAC.unambiguous_dna), id="unknown_seq%d" % rec_counter, name="unknown_seq%d" % rec_counter, description="domesticator-optimized DNA sequence")
	# 		rec_counter += 1
	# 		inserts.append(record)

	# elif mode == "DNA_sequence":
	# 	for input_sequence in inputs:
	# 		record = SeqRecord(Seq(input_sequence,IUPAC.unambiguous_dna), id="unknown_seq%d" % rec_counter, name="unknown_seq%d" % rec_counter, description="domesticator-optimized DNA sequence")
	# 		rec_counter += 1
	# 		inserts.append(record)

	# elif mode == "PDB":
	# 	chain="ABCDEFGHIJKLMNOPQRSTUVWXYZ"
	# 	#parser = PDBParser()
	# 	#ppb=PPBuilder()
	# 	for input_pdb in inputs:
	# 		#for chain_num, polypeptide in enumerate(ppb.build_peptides(parser.get_structure('name', input_pdb))):
	# 		for chain_num, record in enumerate(SeqIO.parse(input_pdb, "pdb-atom")):
	# 			#seq = Seq(reverse_translate(polypeptide.get_sequence()), IUPAC.unambiguous_dna)
	# 			name = os.path.splitext(os.path.basename(input_pdb))[0] + "_" + chain[chain_num]
	# 			#record = SeqRecord(seq, id=name, name=name, description="domesticator-optimized DNA sequence")

	# 			record.seq = Seq(reverse_translate(record.seq), IUPAC.unambiguous_dna)
	# 			record.id=name
	# 			record.name=name
	# 			inserts.append(record)
	# else:
	# 	exit("input mode not recognized: " + args.input_mode)

	return inserts


if __name__ == "__main__":

	parser=argparse.ArgumentParser(prog='domesticator', description='The coolest codon optimizer on the block')

	parser.add_argument('--version', action='version', version='%(prog)s 0.3')

	input_parser = parser.add_argument_group(title="Input Options", description=None)
	#input_parser.add_argument("input",							 			type=str, 	default=None, 			nargs="+",	help="DNA or protein sequence(s) or file(s) to be optimized. Valid inputs are full DNA or protein sequences or fasta or genbank files. Default input is a list of protein sequences. To use a different input type, set --input_mode to the input type.")
	input_parser.add_argument("input",							 			type=str, 	default=None, 			nargs="+",	help="Protein sequence(s) or file(s) to be optimized. Valid inputs are full protein sequences and fasta and pdb files. This should be detected automatically")
	#input_parser.add_argument("--input_mode", 			dest="input_mode", 	type=str, 	default="protein_sequence", 	help="Input mode. %(default)s by default.", choices=["PDB", "DNA_fasta_file", "protein_fasta_file", "DNA_sequence", "protein_sequence"])

	cloning_parser = parser.add_argument_group(title="Cloning Options", description=None)

	cloning_parser.add_argument("--vector", "-v", 		dest="vector", 		type=str, 	default=None, 			metavar="pEXAMPLE.gb",		help="HELP MESSAGE")
	#cloning_parser.add_argument("--destination", "-d", 	dest="destination", type=str, 	default="INSERT", 		metavar="NAME",			help="TODO: flesh this out. Matches the dom_destination feature in the vector")



	optimizer_parser = parser.add_argument_group(title="Optimizer Options", description="These are only used if a vector is not specified or if create_template is set.")
	#Optimization Arguments
	optimizer_parser.add_argument("--no_opt", dest="optimize", action="store_false", default=True, help="Turn this on if you want to insert the input sequence or a naive back-translation of your protein. Not recommended (duh). Turns off all non-critical objectives and constraints")
	optimizer_parser.add_argument("--create_template", dest="create_template", metavar="path/to/file.gb", default=None, help="Provide this with an output filename and the name of the destination annotation in order to perform no optimization and print a template file with the specified optimization instead.")

	#optimizer options
	optimizer_parser.add_argument("--species", dest="species", default="e_coli", help="specifies the codon and dicodon bias tables to use. Defaults to %(default)s", choices=["e_coli", "s_cerevisiae", "h_sapiens"])
	optimizer_parser.add_argument("--codon_optimization_boost", dest="codon_optimization_boost", help="Give a multiplier to the codon optimizer itself. Default to %(default)f", default=1.0)
	optimizer_parser.add_argument("--harmonized", dest="harmonized", help="This will tell the algorithm to choose codons with the same frequency as they appear in nature, otherwise it will pick the best codon as often as possible.", default=False, action="store_true")

	optimizer_parser.add_argument("--avoid_hairpins", dest="avoid_hairpins", type=bool, default=True, help="Removes hairpins according to IDT's definition of a hairpin. A quicker and dirtier alternative to avoid_secondary_structure. Default to %(default)s")

	optimizer_parser.add_argument("--avoid_kmers", dest="kmers", metavar="k", default=9, type=int, help="Repeated sequences can complicate gene synthesis. This prevents repeated sequences of length k. Set to 0 to turn off. Default to %(default)d")
	optimizer_parser.add_argument("--avoid_kmers_boost", dest="avoid_kmers_boost", type=float, default=1.0, help="Give a multiplier to the avoid_kmers term. Default to %(default)f")

	optimizer_parser.add_argument("--avoid_homopolymers", dest="avoid_homopolymers", metavar="len", default=6, type=int, help="homopolymers can complicate synthesis. Prevent homopolymers longer than %(default)d by default. Specify a different length with this option. Set to 0 to turn off")

	optimizer_parser.add_argument("--avoid_patterns", dest="avoid_patterns", nargs="*", metavar="SEQUENCES", help="DNA sequence patterns to avoid", type=str)

	optimizer_parser.add_argument("--avoid_restriction_sites", dest="avoid_restriction_sites", help="Enzymes whose restriction sites you wish to avoid, such as EcoRI or BglII", nargs="*", metavar="enzy", type=str)

	optimizer_parser.add_argument("--constrain_global_GC_content", type=bool, default=True, help="TODO")
	optimizer_parser.add_argument("--global_GC_content_min", type=float, default=0.4, help="TODO")
	optimizer_parser.add_argument("--global_GC_content_max", type=float, default=0.65, help="TODO")

	optimizer_parser.add_argument("--constrain_local_GC_content", type=bool, default=True, help="TODO")
	optimizer_parser.add_argument("--local_GC_content_min", type=float, default=0.25, help="TODO")
	optimizer_parser.add_argument("--local_GC_content_max", type=float, default=0.8, help="TODO")
	optimizer_parser.add_argument("--local_GC_content_window", type=int, default=50, help="TODO")

	optimizer_parser.add_argument("--constrain_terminal_GC_content", type=bool, default=False, help="TODO")
	optimizer_parser.add_argument("--terminal_GC_content_min", type=float, default=0.5, help="TODO")
	optimizer_parser.add_argument("--terminal_GC_content_max", type=float, default=0.9, help="TODO")
	optimizer_parser.add_argument("--terminal_GC_content_window", type=int, default=16, help="TODO")

	optimizer_parser.add_argument("--constrain_CAI", type=bool, default=False, help="TODO")
	optimizer_parser.add_argument("--constrain_CAI_minimum", type=float, default=0.8, help="TODO")

	optimizer_parser.add_argument("--optimize_dicodon_frequency", type=bool, default=False, help="TODO")

	optimizer_parser.add_argument("--avoid_secondary_structure", type=bool, default=False, help="TODO")
	optimizer_parser.add_argument("--avoid_secondary_structure_max_e", type=float, default=-5.0, help="TODO")
	optimizer_parser.add_argument("--avoid_secondary_structure_boost", type=float, default=1.0, help="TODO. Has no effect if --avoid_secondary_structure is not set")

	optimizer_parser.add_argument("--avoid_initiator_secondary_structure", type=bool, default=False, help="TODO")
	optimizer_parser.add_argument("--avoid_initiator_secondary_structure_max_e", type=bool, default=-5.0, help="TODO")
	optimizer_parser.add_argument("--avoid_initiator_secondary_structure_boost", type=float, default=5.0, help="TODO. Has no effect if --avoid_5'_secondary_structure is not set")


	ordering_parser = parser.add_argument_group(title="Ordering Options", description=None)
	ordering_parser.add_argument("--order_type", choices=["gBlocks","genes"], default=None, help="Choose how you'll order your sequences through IDT and you'll get a file called to_order.fasta that you can directly submit")


	output_parser = parser.add_argument_group(title="Output Options", description=None)
	#Output Arguments
	output_parser.add_argument("--output_mode", dest="output_mode", default="terminal", choices=['terminal', 'fasta', 'genbank', 'none'], help="Default: %(default)s\n Choose a mode to export complete sequences in the vector, if specified.")
	output_parser.add_argument("--output_filename", dest="output_filename", help="defaults to %(default)s.fasta or %(default)s.gb", default="domesticator_output")

	args = parser.parse_args()

	destination = "INSERT"

	if args.create_template:
		placeholder = SeqRecord("cgctatgcgaacaaaattgaactggaacgc", name="INSERT")
		naive_construct, objectives, constraints = load_template(args.create_template, placeholder, destination)

		dest_feat = find_annotation(naive_construct, placeholder.name)
		dest_loc = dest_feat.location

		user_objectives, user_constraints = load_user_options(args, dest_loc)

		objectives += user_objectives
		constraints += user_constraints

		print(naive_construct)
		exit(dest_feat)




	inserts = load_inserts(args.input)

	#now load all the custom global constraints and objectives?

	outputs = []

	

	for insert in inserts:
		if args.vector:

			args.output_mode = 'none'
			naive_construct, objectives, constraints = load_template(args.vector, insert, destination)
		else:
			#wasn't given a vector
			naive_construct = insert
			objectives = []
			constraints = []

			location = Location(0, len(insert))

			

			

			objectives, constraints = load_user_options(args, location)
			

		problem = DnaOptimizationProblem(str(naive_construct.seq), constraints=constraints, objectives=objectives)

		if args.create_template:
			record = problem.to_record()
			SeqIO.write(record, args.create_template, "genbank")
			exit()
		else:
			if args.optimize:
				##optimize
				problem.resolve_constraints()
				problem.optimize()
				problem.resolve_constraints(final_check=True)
			else:
				print(problem.constraints_text_summary())
				print(problem.objectives_text_summary())

			mature_construct = naive_construct
			mature_construct.seq = Seq(problem.sequence, alphabet=IUPAC.unambiguous_dna)

			if args.vector:
				template_basename = os.path.basename(args.vector)
				custom_filename = template_basename.replace(destination, mature_construct.name)
				SeqIO.write([mature_construct], custom_filename, "genbank")

			outputs.append(mature_construct)

			#take vector name and replace the destination name with the insert name?

			#does this work right?


	#SO ordering... How does ordering work. 

	#REMEMBER to set the description to "" for easy ordering
	if args.order_type == "gBlocks":
		SeqIO.write([find_annotation(output, "gBlock_to_order").location.extract(output.seq) for output in outputs], "order.fasta", "fasta")
	elif args.order_type == "genes":
		#simply output the thing having been inserted. 
		SeqIO.write([find_annotation(output, "gene_to_order").location.extract(output.seq) for output in outputs], "order.fasta", "fasta")


	#time to handle IO
	if args.output_mode == 'none':
		pass
	elif args.output_mode == 'terminal':
		for output in outputs:
			output.description = ""
			print(output.format("fasta"))
	elif args.output_mode:
		SeqIO.write(mature_construct, args.output_filename, args.output_mode)


	exit()















#77777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777777#


print("loading global constraints")
#load constraints



global_constraints += [
				EnforceGCContent(0.4,0.65), #global
				EnforceGCContent(0.25,0.8,window=50)] #local



if args.avoid_restriction_sites:
	print("avoiding:")
	for enzy in args.avoid_restriction_sites.split(","):
		print(enzy)
		global_constraints.append(AvoidPattern(EnzymeSitePattern(enzy)))

print("loading global objectives")
#load objectives
if args.avoid_kmers > 0:
	global_objectives.append(objectives.MinimizeKmerScore(k = args.avoid_kmers, boost = args.kmer_boost))
if args.is_cds:
	print("optimizing for:")
	for species in args.species.split(","):
		print(species)
		if args.CAI_lower_bound > 0.0:
			global_constraints.append(constraints.ConstrainCAI(species=species, minimum=args.CAI_lower_bound))
		if args.harmonized:
			global_objectives.append(CodonOptimize(species,mode='harmonized')) #NEEDS LOCATION WITH CDS
		else:
			global_objectives.append(CodonOptimize(species,mode='best_codon')) #NEEDS LOCATION WITH CDS
	#global_objectives.append(CodonOptimize(species=args.species,mode='best_codon')) #NEEDS LOCATION WITH CDS

print("begin optimization")
#start optimization



for sr, lc in zip(SeqRecords, local_constraints):
	print("Optimizing %s" % sr.name)
	print(len(sr.seq))
	this_constraints = global_constraints
	if(lc is not None):
		this_constraints += lc
	this_objectives = global_objectives

	print("objectives: %s" % this_objectives)
	print("constraints: %s" % this_constraints)

	problem = DnaOptimizationProblem(
		sequence=str(sr.seq),
		constraints=this_constraints,
		objectives=this_objectives
	)
	
	#print(problem.sequence)
	#print ("\nBefore optimization:\n")
	print (problem.constraints_text_summary(failed_only=True))
	#print (problem.objectives_text_summary())


	#This seems like a great place for GPU calculations
	problem.resolve_constraints()
	problem.optimize()
	problem.resolve_constraints(final_check=True)
	
	#print(problem.sequence)
	if  args.is_cds:
		original_prot = sr.seq.translate()
		optimize_prot = Seq(problem.sequence).translate()
		if(original_prot != optimize_prot):
			print("protein sequence changed before and after optimization")
			print(original_prot)
			print(optimize_prot)
			exit()
	print("Old seq: %s" % sr.seq)
	sr.seq = MutableSeq(problem.sequence, alphabet=IUPAC.unambiguous_dna)
	print("New seq: %s" % sr.seq)
	#print ("\nAfter optimization:\n")
	print (problem.constraints_text_summary(failed_only=True))
	
	#do something else if it's failed!
	#print (problem.objectives_text_summary())
print("finish optimization")
print("outputting")

outname = args.output_filename

args.output_mode = args.output_mode.strip().lower()

#outext = ""
#TODO this is messy. Use BioPython's built in type checker and just clean up input a bit (lower case, etc). Catch errors and then default to terminal.
if args.output_mode == "fasta":
	if outname is None:
		outname = "gblocks.fasta"
	#outext = ".fasta"
	for sr in SeqRecords:
		with open(outname, 'w') as f:
			f.write(sr.format("fasta"))
elif args.output_mode == "genbank":
	if outname is None:
		outname = "gblocks.gb"
	#outext = ".gb"
	sys.exit("not implemented")
else:
	if args.output_mode != "print":
		print("output mode not recognized")
	print("Printing to terminal")
	for sr in SeqRecords:
		print(sr.format("fasta"))
